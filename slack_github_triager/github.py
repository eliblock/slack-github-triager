import json
import re
import subprocess
from dataclasses import dataclass
from enum import Enum


class PrStatus(Enum):
    NEEDS_WORK = "needs_work"
    COMMENTED = "commented"
    APPROVED = "approved"
    MERGED = "merged"


@dataclass(frozen=True)
class PrInfo:
    repo: str
    number: int
    url: str
    status: PrStatus
    author: str
    title: str


COMMON_BOT_REVIEWERS = {
    "cursor",
    "chatgpt-codex-connector",
    "graphite-app",
}
PR_URL_PATTERN = r"https://github\.com/(\w+)/(\w+)/pull/(\d+)"


def check_pr_status(pr_url: str) -> PrInfo:
    match = re.match(PR_URL_PATTERN, pr_url)
    if not match:
        raise ValueError(f"Invalid PR URL: {pr_url}")

    owner, repo, pr_number = match.groups()

    # Get PR data using gh CLI
    result = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            pr_number,
            "--repo",
            f"{owner}/{repo}",
            "--json",
            "state,mergedAt,reviewDecision,author,reviews,title",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Failed to get PR status for {pr_url}: {result.stderr}")

    try:
        pr = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse PR status for {pr_url}") from e

    author = pr.get("author", {}).get("login", "unknown")
    title = pr.get("title", f"{owner}/{repo}#{pr_number}")

    if pr.get("mergedAt"):
        return PrInfo(
            repo=repo,
            number=pr_number,
            url=pr_url,
            status=PrStatus.MERGED,
            author=author,
            title=title,
        )

    # Check review decision
    if pr.get("reviewDecision") == "APPROVED":
        return PrInfo(
            repo=repo,
            number=pr_number,
            url=pr_url,
            status=PrStatus.APPROVED,
            author=author,
            title=title,
        )

    # Check if there are any human reviews (comments) but not approved
    # Filter out bot reviews and self-reviews
    reviews = pr.get("reviews", [])
    human_reviews = [
        review
        for review in reviews
        if (
            review.get("author", {}).get("login", "").lower()
            not in COMMON_BOT_REVIEWERS
            and review.get("author", {}).get("login", "") != author
        )
    ]

    if human_reviews:
        return PrInfo(
            repo=repo,
            number=pr_number,
            url=pr_url,
            status=PrStatus.COMMENTED,
            author=author,
            title=title,
        )

    return PrInfo(
        repo=repo,
        number=pr_number,
        url=pr_url,
        status=PrStatus.NEEDS_WORK,
        author=author,
        title=title,
    )
