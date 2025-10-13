import functools
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any, override

import requests

logger = logging.getLogger(__name__)


################################################################################
# Helpers
################################################################################
@functools.lru_cache()
def get_slack_tokens(subdomain: str, d_cookie: str) -> tuple[str, str]:
    """
    Get session token and enterprise session tokenbased on the d cookie.
    https://papermtn.co.uk/retrieving-and-using-slack-cookies-for-authentication
    """
    response = requests.get(
        f"https://{subdomain}.slack.com",
        cookies={"d": d_cookie},
    )
    response.raise_for_status()

    match = re.search(r'"api_token":"([^"]+)"', response.text)
    if not match:
        raise ValueError("No api_token found in response")

    api_token = match.group(1)

    match = re.search(r'"enterprise_api_token":"([^"]+)"', response.text)
    if not match:
        raise ValueError("No enterprise_api_token found in response")

    enterprise_api_token = match.group(1)

    return api_token, enterprise_api_token


################################################################################
# Slack API Client
################################################################################


class SlackRequestError(Exception):
    pass


def _slack_raise_for_status(response: requests.Response):
    response.raise_for_status()
    if not response.json()["ok"]:
        logger.error(
            f"Slack request failed - Path: {response.request.path_url}, Body: {response.request.body}, Response: {response.text}"
        )

        raise SlackRequestError("non-OK slack response")


class SlackRequestClient:
    def __init__(
        self,
        subdomain: str,
        token: str,
        cookie: str,
        use_bot: bool = False,
        enterprise_token: str | None = None,
    ):
        self.use_bot = use_bot
        self.subdomain = subdomain

        if not self.use_bot and not enterprise_token:
            raise ValueError("enterprise_token is required when user auth is used")

        self.enterprise_token = enterprise_token

        self.session = requests.session()

        if self.use_bot:
            self.session.headers["Authorization"] = f"Bearer {token}"
        else:
            self.session.cookies["d"] = cookie
            self.session.headers["Authorization"] = f"Bearer {token}"

    def _make_slack_request(
        self, method: str, path: str, **kwargs
    ) -> requests.Response:
        assert path and path[0] == "/"

        if self.use_bot:
            url = f"https://slack.com{path}"
        else:
            url = f"https://{self.subdomain}.slack.com{path}"

        while True:
            response = self.session.request(method, url, **kwargs)
            try:
                _slack_raise_for_status(response)
                return response
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    retry_after = int(e.response.headers.get("Retry-After", 1))
                    logger.warning(
                        f"Rate limit hit. Retrying after {retry_after} seconds..."
                    )
                    time.sleep(retry_after)
                else:
                    raise

    def get(self, path: str, **kwargs) -> dict:
        return self._make_slack_request("GET", path, **kwargs).json()

    def paginated_get(self, path: str, **kwargs) -> dict:
        assert path and "?" in path

        response = self._make_slack_request("GET", path, **kwargs)

        while cursor := response.json().get("response_metadata", {}).get("next_cursor"):
            yield response.json()

            response = self._make_slack_request(
                "GET", f"{path}&cursor={cursor}", **kwargs
            )

        return response.json()

    def post(self, path: str, data: list[tuple], **kwargs) -> dict:
        if not self.use_bot:
            data.append(("token", self.enterprise_token))
        return self._make_slack_request("POST", path, data=data, **kwargs).json()


class SlackClientInterface(ABC):
    """
    Abstract base class defining the Slack client interface.
    Compatible with both SlackRequestClient and Slack Bolt SDK.
    """

    @abstractmethod
    def get_channel_name_with_id_fallback(self, *, channel_id: str) -> str:
        pass

    @abstractmethod
    def open_dm(self, *, user_id: str) -> str:
        pass

    @abstractmethod
    def post_message(self, *, channel_id: str, text: str) -> None:
        pass

    @abstractmethod
    def conversation_history(
        self, *, channel_id: str, oldest: str
    ) -> list[dict[str, Any]]:
        pass

    @abstractmethod
    def react(self, *, channel_id: str, timestamp: str, emoji: str) -> None:
        pass


class SlackClient(SlackClientInterface):
    def __init__(self, slack_client: SlackRequestClient):
        self.slack_client = slack_client

    @override
    def get_channel_name_with_id_fallback(self, *, channel_id: str) -> str:
        try:
            return self.slack_client.get(
                path="/api/conversations.info", params={"channel": channel_id}
            )["channel"]["name"]
        except SlackRequestError:
            logger.warning(
                f"Gracefully ignoring error fetching channel name for {channel_id}",
                exc_info=True,
            )
            return channel_id

    @override
    def open_dm(self, *, user_id: str) -> str:
        """Open a DM channel and return the channel ID"""
        return self.slack_client.post(
            "/api/conversations.open", data=[("users", user_id)]
        )["channel"]["id"]

    @override
    def post_message(self, *, channel_id: str, text: str) -> None:
        self.slack_client.post(
            "/api/chat.postMessage",
            data=[
                ("channel", channel_id),
                ("text", text),
                ("unfurl_links", "false"),
                ("unfurl_media", "false"),
            ],
        )

    @override
    def conversation_history(
        self, *, channel_id: str, oldest: str
    ) -> list[dict[str, Any]]:
        return self.slack_client.get(
            "/api/conversations.history",
            params={"channel": channel_id, "oldest": oldest},
        )["messages"]

    @override
    def react(self, *, channel_id: str, timestamp: str, emoji: str) -> None:
        self.slack_client.post(
            "/api/reactions.add",
            data=[
                ("channel", channel_id),
                ("timestamp", timestamp),
                ("name", emoji),
            ],
        )
