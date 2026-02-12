import asyncio
import hashlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Response

from .cache import stats_cache
from .github_fetcher import (
    GitHubRateLimitError,
    GitHubUserNotFoundError,
    UserStats,
    fetch_user_stats,
    validate_username,
)
from .stats_calculator import calculate_rank
from .svg_renderer import render_error_card, render_stats_card
from .themes import resolve_colors

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Per-username locks to prevent duplicate concurrent fetches
_fetch_locks: dict[str, asyncio.Lock] = {}

ALLOWED_USERS_FILE = Path(__file__).parent.parent / "allowed_users.txt"


def _load_allowed_users() -> set[str] | None:
    """Load allowed usernames from env var or file. Returns None if no whitelist configured."""
    # Check env var first
    env_users = os.environ.get("ALLOWED_USERS", "").strip()
    if env_users:
        return {u.strip().lower() for u in env_users.split(",") if u.strip()}

    # Fall back to file
    try:
        text = ALLOWED_USERS_FILE.read_text()
        users = {line.strip().lower() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")}
        if users:
            return users
    except FileNotFoundError:
        pass

    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background cache cleanup on startup."""
    stats_cache.start_background_cleanup()
    logger.info("GitHub User Stats service started")
    yield
    logger.info("GitHub User Stats service shutting down")


app = FastAPI(title="GitHub User Stats", lifespan=lifespan)


@app.get("/api")
async def get_stats(
    username: str = Query(..., description="GitHub username"),
    theme: str | None = Query(None, description="Color theme name"),
    title_color: str | None = Query(None, description="Title color hex"),
    text_color: str | None = Query(None, description="Text color hex"),
    icon_color: str | None = Query(None, description="Icon color hex"),
    bg_color: str | None = Query(None, description="Background color hex"),
    border_color: str | None = Query(None, description="Border color hex"),
    show_icons: bool = Query(True, description="Show icons"),
    hide: str | None = Query(None, description="Comma-separated stats to hide"),
    show: str | None = Query(None, description="Comma-separated extra stats to show"),
    custom_title: str | None = Query(None, description="Custom card title"),
    hide_rank: bool = Query(False, description="Hide rank circle"),
    hide_title: bool = Query(False, description="Hide card title"),
    hide_border: bool = Query(False, description="Hide card border"),
    line_height: int = Query(25, description="Line height between stats"),
    disable_animations: bool = Query(False, description="Disable animations"),
) -> Response:
    """Generate an SVG stats card for a GitHub user."""
    colors = resolve_colors(
        theme=theme,
        title_color=title_color,
        text_color=text_color,
        icon_color=icon_color,
        bg_color=bg_color,
        border_color=border_color,
    )

    # Validate username format
    if not validate_username(username):
        svg = render_error_card("Invalid username format", colors)
        return _svg_response(svg, cache_seconds=60)

    # Check whitelist
    allowed = _load_allowed_users()
    if allowed is not None and username.lower() not in allowed:
        svg = render_error_card("User not authorized", colors)
        return _svg_response(svg, cache_seconds=60)

    # Parse hide/show lists
    hide_list = [s.strip() for s in hide.split(",") if s.strip()] if hide else []
    show_list = [s.strip() for s in show.split(",") if s.strip()] if show else []

    # Try cache first
    cache_key = f"stats:{username.lower()}"
    stats = stats_cache.get(cache_key)

    if stats is None:
        # Dedup concurrent requests for same user
        if username not in _fetch_locks:
            _fetch_locks[username] = asyncio.Lock()

        async with _fetch_locks[username]:
            # Double-check cache after acquiring lock
            stats = stats_cache.get(cache_key)
            if stats is None:
                try:
                    stats = await fetch_user_stats(username)
                    stats_cache.set(cache_key, stats)
                    logger.info("Fetched fresh stats for %s", username)
                except GitHubUserNotFoundError:
                    svg = render_error_card(f"User '{username}' not found on GitHub", colors)
                    return _svg_response(svg, cache_seconds=300)
                except GitHubRateLimitError:
                    # Try stale cache
                    stale_stats, is_stale = stats_cache.get_with_stale(cache_key)
                    if stale_stats is not None:
                        stats = stale_stats
                        logger.info("Serving stale cache for %s (rate limited)", username)
                    else:
                        svg = render_error_card("GitHub API rate limit exceeded. Try again later.", colors)
                        return _svg_response(svg, cache_seconds=60)
                except Exception:
                    logger.exception("Unexpected error fetching stats for %s", username)
                    svg = render_error_card("Failed to fetch GitHub data. Try again later.", colors)
                    return _svg_response(svg, cache_seconds=60)
    else:
        logger.info("Serving cached stats for %s", username)

    svg = render_stats_card(
        stats=stats,
        colors=colors,
        show_icons=show_icons,
        hide=hide_list,
        show=show_list,
        custom_title=custom_title,
        hide_rank=hide_rank,
        hide_title=hide_title,
        hide_border=hide_border,
        line_height=line_height,
        disable_animations=disable_animations,
    )

    return _svg_response(svg, cache_seconds=1800)


def _svg_response(svg: str, cache_seconds: int = 1800) -> Response:
    """Create an SVG response with appropriate headers."""
    etag = hashlib.md5(svg.encode()).hexdigest()
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": f"public, max-age={cache_seconds}",
            "ETag": f'"{etag}"',
        },
    )
