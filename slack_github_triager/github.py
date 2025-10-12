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


def _get_status(pr: dict, author: str) -> PrStatus:
    if pr.get("mergedAt"):
        return PrStatus.MERGED

    if pr.get("reviewDecision") == "APPROVED":
        return PrStatus.APPROVED

    human_reviews = [
        review
        for review in pr.get("reviews", [])
        if (
            review.get("author", {}).get("login", "").lower()
            not in COMMON_BOT_REVIEWERS
            and review.get("author", {}).get("login", "") != author
        )
    ]
    if human_reviews:
        return PrStatus.COMMENTED

    return PrStatus.NEEDS_WORK


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

    author: str = pr.get("author", {}).get("login", "unknown")

    return PrInfo(
        repo=repo,
        number=pr_number,
        url=pr_url,
        status=_get_status(pr, author),
        title=pr.get("title", f"{owner}/{repo}#{pr_number}"),
        author=author,
    )
