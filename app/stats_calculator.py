import math
from dataclasses import dataclass


@dataclass
class RankResult:
    level: str
    percentile: float


def _normal_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _log_normal_cdf(x: float, mu: float = 0, sigma: float = 1) -> float:
    """Log-normal CDF. Returns 0 for x <= 0."""
    if x <= 0:
        return 0.0
    return _normal_cdf((math.log(x) - mu) / sigma)


def _exponential_cdf(x: float, lam: float = 1) -> float:
    """Exponential CDF. Returns 0 for x < 0."""
    if x < 0:
        return 0.0
    return 1 - math.exp(-lam * x)


def calculate_rank(
    total_repos: int = 0,
    total_commits: int = 0,
    contributions: int = 0,
    followers: int = 0,
    prs: int = 0,
    issues: int = 0,
    stars: int = 0,
    reviews: int = 0,
) -> RankResult:
    """Calculate user rank using weighted scoring with statistical CDFs.

    Based on the algorithm from github-readme-stats.
    """
    COMMITS_MEDIAN = 250
    COMMITS_WEIGHT = 2
    PRS_MEDIAN = 50
    PRS_WEIGHT = 3
    ISSUES_MEDIAN = 25
    ISSUES_WEIGHT = 1
    REVIEWS_MEDIAN = 2
    REVIEWS_WEIGHT = 1
    STARS_MEDIAN = 50
    STARS_WEIGHT = 4
    FOLLOWERS_MEDIAN = 10
    FOLLOWERS_WEIGHT = 0.5

    total_weight = (
        COMMITS_WEIGHT
        + PRS_WEIGHT
        + ISSUES_WEIGHT
        + REVIEWS_WEIGHT
        + STARS_WEIGHT
        + FOLLOWERS_WEIGHT
    )

    score = (
        COMMITS_WEIGHT * _exponential_cdf(total_commits / COMMITS_MEDIAN)
        + PRS_WEIGHT * _exponential_cdf(prs / PRS_MEDIAN)
        + ISSUES_WEIGHT * _exponential_cdf(issues / ISSUES_MEDIAN)
        + REVIEWS_WEIGHT * _exponential_cdf(reviews / REVIEWS_MEDIAN)
        + STARS_WEIGHT * _log_normal_cdf(stars / STARS_MEDIAN)
        + FOLLOWERS_WEIGHT * _log_normal_cdf(followers / FOLLOWERS_MEDIAN)
    ) / total_weight

    # Score is 0-1, convert to percentile (100 = best)
    percentile = score * 100

    # Determine grade
    if percentile >= 95:
        level = "S"
    elif percentile >= 85:
        level = "A+"
    elif percentile >= 75:
        level = "A"
    elif percentile >= 60:
        level = "A-"
    elif percentile >= 50:
        level = "B+"
    elif percentile >= 40:
        level = "B"
    elif percentile >= 30:
        level = "B-"
    elif percentile >= 20:
        level = "C+"
    else:
        level = "C"

    return RankResult(level=level, percentile=round(percentile, 1))


def k_format(n: int) -> str:
    """Format number for display: 1234 -> '1.2k', 1000000 -> '1m'."""
    if n < 1000:
        return str(n)
    elif n < 1_000_000:
        val = n / 1000
        if val >= 100:
            return f"{val:.0f}k"
        else:
            formatted = f"{val:.1f}"
            if formatted.endswith(".0"):
                formatted = formatted[:-2]
            return f"{formatted}k"
    else:
        val = n / 1_000_000
        formatted = f"{val:.1f}"
        if formatted.endswith(".0"):
            formatted = formatted[:-2]
        return f"{formatted}m"
