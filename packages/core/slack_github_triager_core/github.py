import json
import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from functools import lru_cache

import jwt
import requests

from slack_github_triager_core.github_client import GithubRequestClient

logger = logging.getLogger(__name__)


class PrStatus(Enum):
    NEEDS_WORK = "needs_work"
    COMMENTED = "commented"
    APPROVED = "approved"
    MERGED = "merged"
    CLOSED = "closed"


@dataclass(frozen=True)
class _PrStatusData:
    state: str
    merged_at: str | None
    review_decision: str | None
    reviews: list[dict]


@dataclass(frozen=True)
class PrInfo:
    owner: str
    repo: str
    number: int
    status: PrStatus
    author: str
    title: str

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}/pull/{self.number}"


COMMON_BOT_REVIEWERS = {
    "cursor",
    "chatgpt-codex-connector",
    "graphite-app",
}
PR_URL_PATTERN = r"https://github\.com/(\w+)/(\w+)/pull/(\d+)"


def _get_status(pr_data: _PrStatusData, author: str) -> PrStatus:
    if pr_data.state.lower() == "closed":
        return PrStatus.CLOSED

    if pr_data.merged_at:
        return PrStatus.MERGED

    # When the GitHub app is used, review_decision may not be populated. In this
    # case, we check for a human-reviewed approval below.
    if pr_data.review_decision and pr_data.review_decision.lower() == "approved":
        return PrStatus.APPROVED

    human_reviews = [
        review
        for review in pr_data.reviews
        if (
            review.get("author", {}).get("login", "").lower()
            not in COMMON_BOT_REVIEWERS
            and review.get("author", {}).get("login", "") != author
        )
    ]
    if human_reviews:
        states = {review["state"] for review in human_reviews}
        if "CHANGES_REQUESTED" in states:
            return PrStatus.COMMENTED
        elif "APPROVED" in states:
            return PrStatus.APPROVED

        return PrStatus.COMMENTED

    return PrStatus.NEEDS_WORK


@lru_cache()
def _get_github_installation_token(app_id: str, private_key: str, org_name: str) -> str:
    # get jwt token
    now = int(datetime.now().timestamp())
    token = jwt.encode(
        {"iat": now - 60, "exp": now + (8 * 60), "iss": app_id},
        key=private_key,
        algorithm="RS256",
    )

    # get installation for org
    response = requests.get(
        "https://api.github.com/app/installations",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
        },
    )
    response.raise_for_status()
    installations = response.json()

    installation_id = None
    for installation in installations:
        if installation.get("account", {}).get("login") == org_name:
            installation_id = installation["id"]
            break

    if installation_id is None:
        raise RuntimeError(f"No installation found for organization '{org_name}'")

    # get installation token
    response = requests.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
        },
    )
    response.raise_for_status()
    return response.json()["token"]


def _check_pr_status_with_github_app(
    owner: str,
    repo: str,
    pr_number: str,
    client: GithubRequestClient,
) -> PrInfo:
    """Get PR info using GitHub API token instead of gh CLI"""
    pr_data = client.get(f"/repos/{owner}/{repo}/pulls/{pr_number}")
    reviews = client.get(f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews")

    author = pr_data["user"]["login"]

    return PrInfo(
        owner=owner,
        repo=repo,
        number=int(pr_number),
        status=_get_status(
            _PrStatusData(
                state=pr_data["state"],
                merged_at=pr_data["merged_at"],
                review_decision=pr_data.get("review_decision"),
                reviews=[
                    {
                        "author": {"login": review["user"]["login"]},
                        "state": review["state"],
                    }
                    for review in reviews
                ],
            ),
            author,
        ),
        title=pr_data["title"],
        author=author,
    )


def _check_pr_status_with_gh_cli(owner: str, repo: str, pr_number: str) -> PrInfo:
    pr_url = f"https://github.com/{owner}/{repo}/pull/{pr_number}"
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
        owner=owner,
        repo=repo,
        number=int(pr_number),
        status=_get_status(
            _PrStatusData(
                state=pr.get("state"),
                merged_at=pr.get("mergedAt"),
                review_decision=pr.get("reviewDecision"),
                reviews=pr.get("reviews", []),
            ),
            author,
        ),
        title=pr.get("title", f"{owner}/{repo}#{pr_number}"),
        author=author,
    )


def check_pr_status(
    pr_url: str, github_client: GithubRequestClient | None = None
) -> PrInfo:
    match = re.match(PR_URL_PATTERN, pr_url)
    if not match:
        raise ValueError(f"Invalid PR URL: {pr_url}")

    owner, repo, pr_number = match.groups()

    if github_client:
        return _check_pr_status_with_github_app(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            client=github_client,
        )

    return _check_pr_status_with_gh_cli(owner=owner, repo=repo, pr_number=pr_number)
