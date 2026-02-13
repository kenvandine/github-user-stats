import asyncio
import logging
import os
import re
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
GITHUB_GRAPHQL = "https://api.github.com/graphql"
USERNAME_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38}$")
MAX_REPO_PAGES = 10

STATS_GRAPHQL_QUERY = """
query($username: String!) {
  user(login: $username) {
    name
    avatarUrl
    followers {
      totalCount
    }
    repositories(ownerAffiliations: OWNER, first: 100, orderBy: {field: STARGAZERS, direction: DESC}) {
      totalCount
      nodes {
        stargazerCount
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      totalRepositoriesWithContributedCommits
    }
  }
  merged: search(query: "author:$USERNAME type:pr is:merged", type: ISSUE) {
    issueCount
  }
  total_prs: search(query: "author:$USERNAME type:pr", type: ISSUE) {
    issueCount
  }
}
"""

REPOS_PAGE_GRAPHQL_QUERY = """
query($username: String!, $cursor: String!) {
  user(login: $username) {
    repositories(ownerAffiliations: OWNER, first: 100, orderBy: {field: STARGAZERS, direction: DESC}, after: $cursor) {
      nodes {
        stargazerCount
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""


class GitHubRateLimitError(Exception):
    pass


class GitHubUserNotFoundError(Exception):
    pass


@dataclass
class UserStats:
    username: str = ""
    name: str = ""
    followers: int = 0
    total_repos: int = 0
    total_stars: int = 0
    total_commits: int = 0
    total_prs: int = 0
    total_prs_merged: int = 0
    total_issues: int = 0
    total_reviews: int = 0
    contributions: int = 0
    avatar_url: str = ""
    from_graphql: bool = False
    errors: list[str] = field(default_factory=list)


def validate_username(username: str) -> bool:
    """Check if username matches GitHub's username rules."""
    return bool(USERNAME_RE.match(username))


def _get_github_token() -> str | None:
    """Get GitHub token from environment."""
    return os.environ.get("GITHUB_TOKEN", "").strip() or None


async def fetch_user_stats(username: str) -> UserStats:
    """Fetch all stats for a GitHub user. Uses GraphQL if a token is available."""
    if not validate_username(username):
        raise GitHubUserNotFoundError(f"Invalid username: {username}")

    token = _get_github_token()
    print(token)
    if token:
        return await _fetch_user_stats_graphql(username, token)
    return await _fetch_user_stats_rest(username)


async def _fetch_user_stats_graphql(username: str, token: str) -> UserStats:
    """Fetch stats via GitHub GraphQL API (requires PAT)."""
    stats = UserStats(username=username)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    # The search query strings need the username substituted as literals
    # (GraphQL variables don't work inside search query strings)
    query = STATS_GRAPHQL_QUERY.replace("$USERNAME", username)

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(
                GITHUB_GRAPHQL,
                headers=headers,
                json={"query": query, "variables": {"username": username}},
            )
            if resp.status_code == 401:
                logger.warning("GitHub token is invalid, falling back to REST API")
                return await _fetch_user_stats_rest(username)
            if resp.status_code == 403:
                _check_rate_limit(resp)
            resp.raise_for_status()

            data = resp.json()

            if "errors" in data:
                errors = data["errors"]
                # Check for user not found
                for err in errors:
                    if err.get("type") == "NOT_FOUND":
                        raise GitHubUserNotFoundError(f"User not found: {username}")
                logger.warning("GraphQL errors for %s: %s", username, errors)
                # Fall back to REST if GraphQL fails
                return await _fetch_user_stats_rest(username)

            user = data["data"]["user"]
            if user is None:
                raise GitHubUserNotFoundError(f"User not found: {username}")

            contrib = user["contributionsCollection"]

            stats.name = user.get("name") or username
            stats.avatar_url = user.get("avatarUrl", "")
            stats.followers = user["followers"]["totalCount"]
            stats.total_repos = user["repositories"]["totalCount"]
            stats.total_commits = (
                contrib["totalCommitContributions"]
                + contrib["restrictedContributionsCount"]
            )
            stats.total_prs = data["data"]["total_prs"]["issueCount"]
            stats.total_prs_merged = data["data"]["merged"]["issueCount"]
            stats.total_issues = contrib["totalIssueContributions"]
            stats.total_reviews = contrib["totalPullRequestReviewContributions"]
            stats.contributions = contrib["totalRepositoriesWithContributedCommits"]

            # Sum stars from repos (first page already in response)
            repos_data = user["repositories"]
            total_stars = sum(node["stargazerCount"] for node in repos_data["nodes"])

            # Paginate remaining repos for star counts
            page_info = repos_data["pageInfo"]
            page = 1
            while page_info["hasNextPage"] and page < MAX_REPO_PAGES:
                page += 1
                page_resp = await client.post(
                    GITHUB_GRAPHQL,
                    headers=headers,
                    json={
                        "query": REPOS_PAGE_GRAPHQL_QUERY,
                        "variables": {
                            "username": username,
                            "cursor": page_info["endCursor"],
                        },
                    },
                )
                if page_resp.status_code == 403:
                    _check_rate_limit(page_resp)
                page_resp.raise_for_status()
                page_data = page_resp.json()
                if "errors" in page_data:
                    break
                repos_page = page_data["data"]["user"]["repositories"]
                total_stars += sum(
                    node["stargazerCount"] for node in repos_page["nodes"]
                )
                page_info = repos_page["pageInfo"]

            stats.total_stars = total_stars

        except (GitHubUserNotFoundError, GitHubRateLimitError):
            raise
        except Exception as e:
            logger.warning(
                "GraphQL fetch failed for %s: %s, falling back to REST", username, e
            )
            return await _fetch_user_stats_rest(username)

    stats.from_graphql = True
    logger.info("Fetched stats for %s via GraphQL", username)
    return stats


async def _fetch_user_stats_rest(username: str) -> UserStats:
    """Fetch stats via REST API (unauthenticated fallback)."""
    stats = UserStats(username=username)
    headers = {"Accept": "application/vnd.github.v3+json"}

    token = _get_github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(
        base_url=GITHUB_API,
        headers=headers,
        timeout=15.0,
        follow_redirects=True,
    ) as client:
        await asyncio.gather(
            _fetch_core_data(client, username, stats),
            _fetch_search_data(client, username, stats),
        )

    return stats


async def _fetch_core_data(
    client: httpx.AsyncClient, username: str, stats: UserStats
) -> None:
    """Fetch data from core API endpoints (shared rate limit pool)."""
    # User profile first - if this 404s, user doesn't exist
    await _fetch_user_profile(client, username, stats)

    # Then repos and events in parallel
    await asyncio.gather(
        _fetch_repos(client, username, stats),
        _fetch_events(client, username, stats),
    )


async def _fetch_user_profile(
    client: httpx.AsyncClient, username: str, stats: UserStats
) -> None:
    """Fetch user profile data."""
    try:
        resp = await client.get(f"/users/{username}")
        if resp.status_code == 404:
            raise GitHubUserNotFoundError(f"User not found: {username}")
        if resp.status_code == 403:
            _check_rate_limit(resp)
        resp.raise_for_status()
        data = resp.json()
        stats.name = data.get("name") or username
        stats.followers = data.get("followers", 0)
        stats.total_repos = data.get("public_repos", 0)
        stats.avatar_url = data.get("avatar_url", "")
    except (GitHubUserNotFoundError, GitHubRateLimitError):
        raise
    except Exception as e:
        logger.warning("Failed to fetch profile for %s: %s", username, e)
        stats.errors.append(f"profile: {e}")


async def _fetch_repos(
    client: httpx.AsyncClient, username: str, stats: UserStats
) -> None:
    """Fetch all repos to count total stars (paginated)."""
    total_stars = 0
    page = 1
    try:
        while page <= MAX_REPO_PAGES:
            resp = await client.get(
                f"/users/{username}/repos",
                params={"per_page": 100, "page": page, "type": "owner"},
            )
            if resp.status_code == 403:
                _check_rate_limit(resp)
            resp.raise_for_status()
            repos = resp.json()
            if not repos:
                break
            for repo in repos:
                total_stars += repo.get("stargazers_count", 0)
            if len(repos) < 100:
                break
            page += 1
        stats.total_stars = total_stars
    except GitHubRateLimitError:
        raise
    except Exception as e:
        logger.warning("Failed to fetch repos for %s: %s", username, e)
        stats.errors.append(f"repos: {e}")


async def _fetch_events(
    client: httpx.AsyncClient, username: str, stats: UserStats
) -> None:
    """Fetch public events for reviews and contribution counts."""
    try:
        resp = await client.get(
            f"/users/{username}/events/public", params={"per_page": 100}
        )
        if resp.status_code == 403:
            _check_rate_limit(resp)
        resp.raise_for_status()
        events = resp.json()

        reviews = 0
        contributed_repos = set()
        for event in events:
            event_type = event.get("type", "")
            repo_name = event.get("repo", {}).get("name", "")

            if event_type == "PullRequestReviewEvent":
                reviews += 1
            if repo_name and not repo_name.startswith(f"{username}/"):
                contributed_repos.add(repo_name)

        stats.total_reviews = reviews
        stats.contributions = len(contributed_repos)
    except GitHubRateLimitError:
        raise
    except Exception as e:
        logger.warning("Failed to fetch events for %s: %s", username, e)
        stats.errors.append(f"events: {e}")


async def _fetch_search_data(
    client: httpx.AsyncClient, username: str, stats: UserStats
) -> None:
    """Fetch data from search API endpoints (separate rate limit pool)."""
    # Run search queries with small delays to be gentle on the search rate limit
    # (10 req/min for unauthenticated)
    searches = [
        _fetch_search_commits(client, username, stats),
        _fetch_search_prs(client, username, stats),
        _fetch_search_merged_prs(client, username, stats),
        _fetch_search_issues(client, username, stats),
    ]
    await asyncio.gather(*searches, return_exceptions=True)


async def _fetch_search_commits(
    client: httpx.AsyncClient, username: str, stats: UserStats
) -> None:
    """Fetch total commit count via search API."""
    try:
        resp = await client.get(
            "/search/commits",
            params={"q": f"author:{username}", "per_page": 1},
        )
        if resp.status_code == 403:
            _check_rate_limit(resp)
        if resp.status_code == 422:
            # Search validation error, skip gracefully
            stats.errors.append("commits: search validation error")
            return
        resp.raise_for_status()
        stats.total_commits = resp.json().get("total_count", 0)
    except GitHubRateLimitError:
        raise
    except Exception as e:
        logger.warning("Failed to search commits for %s: %s", username, e)
        stats.errors.append(f"commits: {e}")


async def _fetch_search_prs(
    client: httpx.AsyncClient, username: str, stats: UserStats
) -> None:
    """Fetch total PR count via search API."""
    try:
        resp = await client.get(
            "/search/issues",
            params={"q": f"author:{username} type:pr", "per_page": 1},
        )
        if resp.status_code == 403:
            _check_rate_limit(resp)
        if resp.status_code == 422:
            stats.errors.append("prs: search validation error")
            return
        resp.raise_for_status()
        stats.total_prs = resp.json().get("total_count", 0)
    except GitHubRateLimitError:
        raise
    except Exception as e:
        logger.warning("Failed to search PRs for %s: %s", username, e)
        stats.errors.append(f"prs: {e}")


async def _fetch_search_merged_prs(
    client: httpx.AsyncClient, username: str, stats: UserStats
) -> None:
    """Fetch merged PR count via search API."""
    try:
        resp = await client.get(
            "/search/issues",
            params={"q": f"author:{username} type:pr is:merged", "per_page": 1},
        )
        if resp.status_code == 403:
            _check_rate_limit(resp)
        if resp.status_code == 422:
            stats.errors.append("merged_prs: search validation error")
            return
        resp.raise_for_status()
        stats.total_prs_merged = resp.json().get("total_count", 0)
    except GitHubRateLimitError:
        raise
    except Exception as e:
        logger.warning("Failed to search merged PRs for %s: %s", username, e)
        stats.errors.append(f"merged_prs: {e}")


async def _fetch_search_issues(
    client: httpx.AsyncClient, username: str, stats: UserStats
) -> None:
    """Fetch total issue count via search API."""
    try:
        resp = await client.get(
            "/search/issues",
            params={"q": f"author:{username} type:issue", "per_page": 1},
        )
        if resp.status_code == 403:
            _check_rate_limit(resp)
        if resp.status_code == 422:
            stats.errors.append("issues: search validation error")
            return
        resp.raise_for_status()
        stats.total_issues = resp.json().get("total_count", 0)
    except GitHubRateLimitError:
        raise
    except Exception as e:
        logger.warning("Failed to search issues for %s: %s", username, e)
        stats.errors.append(f"issues: {e}")


def _check_rate_limit(resp: httpx.Response) -> None:
    """Raise GitHubRateLimitError if response indicates rate limiting."""
    remaining = resp.headers.get("x-ratelimit-remaining", "")
    if remaining == "0" or "rate limit" in resp.text.lower():
        raise GitHubRateLimitError("GitHub API rate limit exceeded")
