from dataclasses import dataclass
from datetime import datetime, timedelta

from slack_github_triager_core.slack_client import SlackClientInterface


@dataclass(frozen=True)
class ChannelInfo:
    id: str
    name_with_id_fallback: str | None = None


def emoji_react(
    client: SlackClientInterface, channel_id: str, timestamp: str, emoji: str
):
    client.react(channel_id=channel_id, timestamp=timestamp, emoji=emoji)


def has_recent_matching_message(
    client: SlackClientInterface,
    channel_id: str,
    search_text: str,
    check_range: timedelta | None = None,
) -> bool:
    check_range = check_range or timedelta(hours=12)

    return any(
        search_text in msg.get("text", "")
        for msg in client.conversation_history(
            channel_id=channel_id,
            oldest=str((datetime.now() - check_range).timestamp()),
        )
    )


def _format_relative_time(timestamp: float) -> str:
    dt = datetime.fromtimestamp(timestamp)
    now = datetime.now()
    diff = now - dt

    # If less than a minute ago
    if diff.total_seconds() < 60:
        return "just now"

    # If less than an hour ago
    elif diff.total_seconds() < 3600:
        minutes = int(diff.total_seconds() / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"

    # If today
    elif dt.date() == now.date():
        return f"today at {dt.strftime('%I:%M%p').lower()}"

    # If yesterday
    elif (now.date() - dt.date()).days == 1:
        return f"yesterday at {dt.strftime('%I:%M%p').lower()}"

    # If within the last week
    elif diff.days < 7:
        day_name = dt.strftime("%A")
        return f"{day_name} at {dt.strftime('%I:%M%p').lower()}"

    # Otherwise, use full date
    else:
        return dt.strftime("%B %d at %I:%M%p").lower()


SLACK_DATE_FORMAT_STRING_WITH_BRACES = "{date_short_pretty} at {time}"


def slack_format_relative_time(timestamp: float) -> str:
    return f"<!date^{int(timestamp)}^{SLACK_DATE_FORMAT_STRING_WITH_BRACES}|{_format_relative_time(timestamp)}>"
