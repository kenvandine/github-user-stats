from html import escape

from .github_fetcher import UserStats
from .icons import ICONS
from .stats_calculator import RankResult, calculate_rank, k_format
from .themes import ThemeColors


def render_stats_card(
    stats: UserStats,
    colors: ThemeColors,
    show_icons: bool = True,
    hide: list[str] | None = None,
    show: list[str] | None = None,
    custom_title: str | None = None,
    hide_rank: bool = False,
    hide_title: bool = False,
    hide_border: bool = False,
    line_height: int = 25,
    disable_animations: bool = False,
) -> str:
    """Render an SVG stats card for a GitHub user."""
    hide_set = set(hide or [])
    show_set = set(show or [])

    rank = calculate_rank(
        total_repos=stats.total_repos,
        total_commits=stats.total_commits,
        contributions=stats.contributions,
        followers=stats.followers,
        prs=stats.total_prs,
        issues=stats.total_issues,
        stars=stats.total_stars,
        reviews=stats.total_reviews,
    )

    # Build stat rows (may include section headings when GraphQL data)
    stat_items = _build_stat_items(stats, hide_set, show_set)

    # Calculate dimensions
    card_width = 495
    title_y = 35
    stats_start_y = 55 if not hide_title else 25
    card_height = stats_start_y + len(stat_items) * line_height + 30
    card_height = max(card_height, 195 if not hide_rank else 150)

    title = escape(custom_title or f"{stats.name}'s GitHub Stats")

    border_stroke = "" if hide_border else f'stroke="#{colors.border_color}" stroke-opacity="1"'

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{card_width}" height="{card_height}" viewBox="0 0 {card_width} {card_height}" fill="none">',
        _build_style(colors, disable_animations, line_height),
        f'<rect x="0.5" y="0.5" rx="4.5" width="{card_width - 1}" height="{card_height - 1}" fill="#{colors.bg_color}" {border_stroke}/>',
    ]

    if not hide_title:
        parts.append(
            f'<g transform="translate(25, {title_y})">'
            f'<text class="header" x="0" y="0" data-testid="header">{title}</text>'
            f"</g>"
        )

    # Stat rows (with optional section headings)
    for i, item in enumerate(stat_items):
        y = stats_start_y + i * line_height
        delay = i * 150
        if item.get("type") == "heading":
            parts.append(_render_section_heading(item, y, colors, delay, disable_animations))
        else:
            parts.append(_render_stat_row(item, y, show_icons, colors, delay, disable_animations))

    # Rank circle
    if not hide_rank:
        parts.append(_render_rank_circle(rank, colors, card_height, disable_animations))

    parts.append("</svg>")
    return "\n".join(parts)


def render_error_card(message: str, colors: ThemeColors | None = None) -> str:
    """Render an SVG error card."""
    if colors is None:
        from .themes import THEMES
        colors = THEMES["default"]

    escaped_msg = escape(message)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="495" height="120" viewBox="0 0 495 120" fill="none">'
        "<style>"
        f'.header {{ font: 600 18px "Segoe UI", Ubuntu, Sans-Serif; fill: #{colors.title_color}; }}'
        f'.message {{ font: 400 14px "Segoe UI", Ubuntu, Sans-Serif; fill: #{colors.text_color}; }}'
        "</style>"
        f'<rect x="0.5" y="0.5" rx="4.5" width="494" height="119" fill="#{colors.bg_color}" '
        f'stroke="#{colors.border_color}"/>'
        '<g transform="translate(25, 35)">'
        '<text class="header">Error</text>'
        f'<text class="message" y="30">{escaped_msg}</text>'
        "</g>"
        "</svg>"
    )


def _build_stat_items(
    stats: UserStats, hide_set: set[str], show_set: set[str]
) -> list[dict]:
    """Build the list of stat items to display.

    When stats come from GraphQL, items are grouped under
    'All Time' and 'Last 12 Months' section headings.
    """
    if stats.from_graphql:
        return _build_stat_items_graphql(stats, hide_set, show_set)
    return _build_stat_items_flat(stats, hide_set, show_set)


def _build_stat_items_flat(
    stats: UserStats, hide_set: set[str], show_set: set[str]
) -> list[dict]:
    """Build a flat list of stat items (REST fallback)."""
    items = []

    default_stats = [
        ("stars", "Total Stars", stats.total_stars, "star"),
        ("commits", "Total Commits", stats.total_commits, "commits"),
        ("prs", "Total PRs", stats.total_prs, "prs"),
        ("issues", "Total Issues", stats.total_issues, "issues"),
        ("contribs", "Contributed to", stats.contributions, "contribs"),
    ]

    optional_stats = [
        ("reviews", "Total Reviews", stats.total_reviews, "reviews"),
        ("prs_merged", "PRs Merged", stats.total_prs_merged, "prs"),
        (
            "prs_merged_percentage",
            "PRs Merged %",
            _calc_merged_pct(stats.total_prs_merged, stats.total_prs),
            "prs",
        ),
    ]

    for key, label, value, icon in default_stats:
        if key not in hide_set:
            display = k_format(value) if isinstance(value, int) else value
            items.append({"label": label, "value": display, "icon": icon})

    for key, label, value, icon in optional_stats:
        if key in show_set:
            display = k_format(value) if isinstance(value, int) else value
            items.append({"label": label, "value": display, "icon": icon})

    return items


def _build_stat_items_graphql(
    stats: UserStats, hide_set: set[str], show_set: set[str]
) -> list[dict]:
    """Build stat items grouped into All Time / Last 12 Months sections."""
    items = []

    # --- All Time (from search + profile) ---
    alltime_stats = [
        ("stars", "Total Stars", stats.total_stars, "star"),
        ("prs", "Total PRs", stats.total_prs, "prs"),
    ]
    alltime_optional = [
        ("prs_merged", "PRs Merged", stats.total_prs_merged, "prs"),
        (
            "prs_merged_percentage",
            "PRs Merged %",
            _calc_merged_pct(stats.total_prs_merged, stats.total_prs),
            "prs",
        ),
    ]

    alltime_rows = []
    for key, label, value, icon in alltime_stats:
        if key not in hide_set:
            display = k_format(value) if isinstance(value, int) else value
            alltime_rows.append({"label": label, "value": display, "icon": icon})
    for key, label, value, icon in alltime_optional:
        if key in show_set:
            display = k_format(value) if isinstance(value, int) else value
            alltime_rows.append({"label": label, "value": display, "icon": icon})

    if alltime_rows:
        items.append({"type": "heading", "label": "All Time"})
        items.extend(alltime_rows)

    # --- Last 12 Months (from contributionsCollection) ---
    recent_stats = [
        ("commits", "Total Commits", stats.total_commits, "commits"),
        ("issues", "Total Issues", stats.total_issues, "issues"),
        ("contribs", "Contributed to", stats.contributions, "contribs"),
    ]
    recent_optional = [
        ("reviews", "Total Reviews", stats.total_reviews, "reviews"),
    ]

    recent_rows = []
    for key, label, value, icon in recent_stats:
        if key not in hide_set:
            display = k_format(value) if isinstance(value, int) else value
            recent_rows.append({"label": label, "value": display, "icon": icon})
    for key, label, value, icon in recent_optional:
        if key in show_set:
            display = k_format(value) if isinstance(value, int) else value
            recent_rows.append({"label": label, "value": display, "icon": icon})

    if recent_rows:
        items.append({"type": "heading", "label": "Last 12 Months"})
        items.extend(recent_rows)

    return items


def _calc_merged_pct(merged: int, total: int) -> str:
    """Calculate merged PR percentage."""
    if total == 0:
        return "0%"
    return f"{(merged / total) * 100:.1f}%"


def _build_style(colors: ThemeColors, disable_animations: bool, line_height: int) -> str:
    """Build the CSS style block."""
    animation_css = ""
    if not disable_animations:
        animation_css = """
      @keyframes fadeInAnimation {
        from { opacity: 0; }
        to { opacity: 1; }
      }
      @keyframes growWidthAnimation {
        from { width: 0; }
        to { width: 100%; }
      }
      @keyframes rankAnimation {
        from { stroke-dashoffset: 251.32; }
      }
      @keyframes scaleInAnimation {
        from { transform: translate(-5px, 5px) scale(0); }
        to { transform: translate(-5px, 5px) scale(1); }
      }
      .stat-row {
        animation: fadeInAnimation 0.3s ease-in-out forwards;
        opacity: 0;
      }
      .rank-circle-rim {
        animation: rankAnimation 1s forwards ease-in-out;
      }
      .rank-text {
        animation: scaleInAnimation 0.3s ease-in-out forwards;
      }"""

    return (
        "<style>"
        f'.header {{ font: 600 18px "Segoe UI", Ubuntu, Sans-Serif; fill: #{colors.title_color}; animation: fadeInAnimation 0.8s ease-in-out forwards; }}'
        f'.stat-label {{ font: 400 14px "Segoe UI", Ubuntu, Sans-Serif; fill: #{colors.text_color}; }}'
        f'.stat-value {{ font: 700 14px "Segoe UI", Ubuntu, Sans-Serif; fill: #{colors.text_color}; }}'
        f'.section-heading {{ font: 700 14px "Segoe UI", Ubuntu, Sans-Serif; fill: #{colors.text_color}; }}'
        f'.rank-letter {{ font: 800 24px "Segoe UI", Ubuntu, Sans-Serif; fill: #{colors.text_color}; }}'
        f'.rank-percentile {{ font: 400 12px "Segoe UI", Ubuntu, Sans-Serif; fill: #{colors.text_color}; }}'
        f"{animation_css}"
        "</style>"
    )


def _render_section_heading(
    item: dict, y: int, colors: ThemeColors, delay: int, disable_animations: bool
) -> str:
    """Render a bold section heading row."""
    anim_style = "" if disable_animations else f' style="animation-delay: {delay}ms"'
    row_class = "stat-row" if not disable_animations else ""

    return (
        f'<g class="{row_class}" transform="translate(25, {y})"{anim_style}>'
        f'<text class="section-heading" x="0" y="0">{escape(item["label"])}</text>'
        f"</g>"
    )


def _render_stat_row(
    item: dict, y: int, show_icons: bool, colors: ThemeColors, delay: int, disable_animations: bool
) -> str:
    """Render a single stat row."""
    anim_style = "" if disable_animations else f' style="animation-delay: {delay}ms"'
    row_class = "stat-row" if not disable_animations else ""

    parts = [f'<g class="{row_class}" transform="translate(25, {y})"{anim_style}>']

    x_offset = 0
    if show_icons:
        icon_path = ICONS.get(item["icon"], "")
        if icon_path:
            parts.append(
                f'<svg x="0" y="-13" width="16" height="16" viewBox="0 0 16 16" fill="#{colors.icon_color}">'
                f'<path d="{icon_path}"/>'
                f"</svg>"
            )
        x_offset = 25

    parts.append(
        f'<text class="stat-label" x="{x_offset}" y="0">{escape(item["label"])}:</text>'
    )
    parts.append(
        f'<text class="stat-value" x="220" y="0">{escape(str(item["value"]))}</text>'
    )
    parts.append("</g>")

    return "".join(parts)


def _render_rank_circle(
    rank: RankResult, colors: ThemeColors, card_height: int, disable_animations: bool
) -> str:
    """Render the rank circle on the right side of the card."""
    cx = 425
    cy = card_height / 2
    r = 40
    circumference = 2 * 3.14159 * r
    progress = (rank.percentile / 100) * circumference
    dashoffset = circumference - progress

    anim_attr = "" if disable_animations else ""
    rank_circle_class = "rank-circle-rim" if not disable_animations else ""

    return (
        f'<g transform="translate({cx}, {cy})">'
        f'<circle r="{r}" cx="0" cy="0" fill="none" stroke="#{colors.text_color}" stroke-width="6" stroke-opacity="0.2"/>'
        f'<circle class="{rank_circle_class}" r="{r}" cx="0" cy="0" fill="none" '
        f'stroke="#{colors.icon_color}" stroke-width="6" '
        f'stroke-dasharray="{circumference}" stroke-dashoffset="{dashoffset}" '
        f'stroke-linecap="round" transform="rotate(-90)"/>'
        f'<text class="rank-letter" text-anchor="middle" dominant-baseline="central" y="-5">'
        f"{escape(rank.level)}</text>"
        f'<text class="rank-percentile" text-anchor="middle" dominant-baseline="central" y="15">'
        f"Top {rank.percentile}%</text>"
        f"</g>"
    )
