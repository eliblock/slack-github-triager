from dataclasses import dataclass
from datetime import datetime, timedelta

from slack_github_triager.slack_client import (
    SlackRequestClient,
)


@dataclass(frozen=True)
class ChannelInfo:
    id: str
    name: str


def emoji_react(
    client: SlackRequestClient, channel_id: str, timestamp: str, emoji: str
):
    pass
    client.post(
        "/api/reactions.add",
        data=[
            ("channel", channel_id),
            ("timestamp", timestamp),
            ("name", emoji),
        ],
    )


def has_recent_matching_message(
    client: SlackRequestClient,
    channel_id: str,
    search_text: str,
    check_range: timedelta | None = None,
) -> bool:
    check_range = check_range or timedelta(hours=12)

    return any(
        search_text in msg.get("text", "")
        for msg in client.get(
            "/api/conversations.history",
            params={
                "channel": channel_id,
                "oldest": str((datetime.now() - check_range).timestamp()),
            },
        )["messages"]
    )
