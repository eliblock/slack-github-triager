import functools
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .github import (
    PR_URL_PATTERN,
    PrInfo,
    PrStatus,
    check_pr_status,
)
from .github_client import GithubRequestClient
from .slack import (
    ChannelInfo,
    emoji_react,
    has_recent_matching_message,
    slack_format_relative_time,
)
from .slack_client import (
    SlackClientInterface,
)

logger = logging.getLogger(__name__)
################################################################################
# Data classes
################################################################################


@dataclass(frozen=True)
class ReactionConfiguration:
    bot_approved: str = "white_check_mark"
    bot_considers_approved: set[str] = field(
        default_factory=lambda: {"white_check_mark"}
    )

    bot_merged: str = "package"
    bot_considers_merged: set[str] = field(default_factory=lambda: {"package"})

    bot_commented: str = "speech_balloon"
    bot_considers_commented: set[str] = field(
        default_factory=lambda: {"speech_balloon"}
    )

    bot_closed: str = "x"
    bot_considers_closed: set[str] = field(default_factory=lambda: {"x"})

    bot_confused: str = "robot_face"


@dataclass(frozen=True)
class ProcessedSlackMessage:
    pr_urls: frozenset[str]
    reactions: frozenset[str]
    message_has_multiple_prs: bool
    ts: str
    channel_id: str


@dataclass(frozen=True)
class PrSlackInfo:
    pr: PrInfo
    message: ProcessedSlackMessage

    def generate_bullet(
        self, slack_subdomain: str, reaction_configuration: ReactionConfiguration
    ) -> str:
        """Generate a bullet point with PR link and message link."""

        pr_link = f"<{self.pr.url}|{self.pr.title}>"
        original_thread_link = f"<https://{slack_subdomain}web.slack.com/archives/{self.message.channel_id}/p{self.message.ts.replace('.', '')}|thread> {slack_format_relative_time(float(self.message.ts))}"
        base = f"{pr_link} by {self.pr.author} in `{self.pr.repo}` ({original_thread_link})"

        match self.pr.status:
            case PrStatus.CLOSED:
                prefix = f"(:{reaction_configuration.bot_closed}:) "
            case PrStatus.COMMENTED:
                prefix = f"(:{reaction_configuration.bot_commented}:) "
            case PrStatus.APPROVED:
                prefix = f"(:{reaction_configuration.bot_approved}:) "
            case PrStatus.MERGED:
                prefix = f"(:{reaction_configuration.bot_merged}:) "
            case _:
                prefix = ""

        return f"• {prefix}{base}"


@dataclass(frozen=True)
class ChannelSummary:
    channel: ChannelInfo
    pr_infos: tuple[
        PrSlackInfo, ...
    ]  # tuple for immutability to enable @functools.lru_cache

    @functools.lru_cache()
    def pr_infos_for_status(self, status: PrStatus) -> list[PrSlackInfo]:
        return sorted(
            [pr_info for pr_info in self.pr_infos if pr_info.pr.status == status],
            key=lambda x: (x.pr.repo, x.message.ts),
        )


################################################################################
# Message building & sending
################################################################################
AUTOMATION_MESSAGE_PREFIX = ":robot_dance: I am an automation!"


def build_dm_message(
    slack_subdomain: str,
    reaction_configuration: ReactionConfiguration,
    channel_summaries: list[ChannelSummary],
    start_time: float,
    end_time: float,
):
    """Build the comprehensive DM message with all channels."""
    start_relative = slack_format_relative_time(start_time)
    end_relative = slack_format_relative_time(end_time)

    message_lines = [
        f"{AUTOMATION_MESSAGE_PREFIX} I reviewed messages from {start_relative} to {end_relative}. The following PRs need attention:"
    ]

    # Show all channels, even those with no work needed
    for summary in channel_summaries:
        message_lines.append(
            f"\n\n<#{summary.channel.id}|{summary.channel.name_with_id_fallback}>:"
        )
        needs_work_pr_infos = summary.pr_infos_for_status(PrStatus.NEEDS_WORK)
        commented_pr_infos = summary.pr_infos_for_status(PrStatus.COMMENTED)

        if needs_work_pr_infos or commented_pr_infos:
            # Channel has PRs needing attention - show NEEDS_WORK first, then COMMENTED
            for pr_info in needs_work_pr_infos:
                message_lines.append(
                    pr_info.generate_bullet(slack_subdomain, reaction_configuration)
                )
            for pr_info in commented_pr_infos:
                message_lines.append(
                    pr_info.generate_bullet(slack_subdomain, reaction_configuration)
                )
        else:
            # No PRs needing attention in this channel
            message_lines.append("• No PRs need attention")

    return "\n".join(message_lines)


def send_dm_message(
    client: SlackClientInterface,
    slack_subdomain: str,
    reaction_configuration: ReactionConfiguration,
    channel_summaries: list[ChannelSummary],
    start_time: float,
    end_time: float,
    user_ids: list[str],
    suppress_message: bool = False,
) -> None:
    # Send DM with comprehensive summary
    dm_text = build_dm_message(
        slack_subdomain, reaction_configuration, channel_summaries, start_time, end_time
    )

    # Open DM channel and send message
    for user_id in user_ids:
        dm_channel = client.open_dm(user_id=user_id)
        if not suppress_message:
            client.post_message(channel_id=dm_channel, text=dm_text)

    if suppress_message:
        logger.debug(f"output suppressed! Would have sent: '{dm_text}'")
    logger.info(
        f"{'Would have sent' if suppress_message else 'Sent'} summary DM to {len(user_ids)} users: {', '.join(user_ids)}"
    )


def build_channel_message(
    slack_subdomain: str,
    reaction_configuration: ReactionConfiguration,
    prs: list[PrSlackInfo],
    channel: ChannelInfo,
    start_time: float,
    end_time: float,
) -> str:
    """Build a channel-specific summary message."""
    message_lines = [
        f"{AUTOMATION_MESSAGE_PREFIX} I reviewed messages in <#{channel.id}|{channel.name_with_id_fallback}> "
        + f"from {slack_format_relative_time(start_time)} to "
        + f"{slack_format_relative_time(end_time)} :robot_dance:.\n\n"
        + "It looks like the following PRs might require attention:"
    ]

    for pr_info in prs:
        message_lines.append(
            pr_info.generate_bullet(slack_subdomain, reaction_configuration)
        )

    return "\n".join(message_lines)


def send_channel_message(
    client: SlackClientInterface,
    slack_subdomain: str,
    reaction_configuration: ReactionConfiguration,
    summary: ChannelSummary,
    start_time: float,
    end_time: float,
    suppress_message: bool = False,
) -> None:
    # Skip if there's a recent automation message
    if has_recent_matching_message(
        client, summary.channel.id, AUTOMATION_MESSAGE_PREFIX
    ):
        return

    needs_work_prs = summary.pr_infos_for_status(PrStatus.NEEDS_WORK)
    commented_prs = summary.pr_infos_for_status(PrStatus.COMMENTED)
    all_review_prs = needs_work_prs + commented_prs

    # Skip if nothing to be done
    if not all_review_prs:
        return

    # Build and send channel message
    channel_text = build_channel_message(
        slack_subdomain,
        reaction_configuration,
        all_review_prs,
        summary.channel,
        start_time,
        end_time,
    )

    if not suppress_message:
        client.post_message(channel_id=summary.channel.id, text=channel_text)

    else:
        logger.debug(f"output suppressed! Would have sent: '{channel_text}'")
    logger.info(
        f"{'Would have sent' if suppress_message else 'Sent'} summary to #{summary.channel.name_with_id_fallback} with {len(all_review_prs)} PRs"
    )


################################################################################
# Reaction handling
################################################################################


def react_to_pr_infos(
    client: SlackClientInterface,
    channel_summary: ChannelSummary,
    reaction_configuration: ReactionConfiguration | None = None,
):
    """React to messages based on PR status using stored data."""

    reaction_configuration = reaction_configuration or ReactionConfiguration()

    messages_reacted: set[tuple[str, str]] = set()
    for pr_info in channel_summary.pr_infos:
        message_key = (channel_summary.channel.id, pr_info.message.ts)

        # If a Slack message links multiple PRs, react to it to acknowledge but
        # not hint at statuses.
        if pr_info.message.message_has_multiple_prs:
            if (
                message_key not in messages_reacted
                and reaction_configuration.bot_confused not in pr_info.message.reactions
            ):
                emoji_react(
                    client,
                    channel_id=channel_summary.channel.id,
                    timestamp=pr_info.message.ts,
                    emoji=reaction_configuration.bot_confused,
                )
                messages_reacted.add(message_key)
            continue

        # Skip if already reacted to this message
        if message_key in messages_reacted:
            continue

        # Check if already reacted appropriately
        if (
            pr_info.pr.status == PrStatus.CLOSED
            and reaction_configuration.bot_considers_closed & pr_info.message.reactions
        ):
            continue
        elif (
            pr_info.pr.status == PrStatus.APPROVED
            and reaction_configuration.bot_considers_approved
            & pr_info.message.reactions
        ):
            continue
        elif (
            pr_info.pr.status == PrStatus.MERGED
            and reaction_configuration.bot_considers_merged & pr_info.message.reactions
        ):
            continue
        elif (
            pr_info.pr.status == PrStatus.COMMENTED
            and reaction_configuration.bot_considers_commented
            & pr_info.message.reactions
        ):
            continue

        # React based on status
        if emoji := {
            PrStatus.CLOSED: reaction_configuration.bot_closed,
            PrStatus.APPROVED: reaction_configuration.bot_approved,
            PrStatus.MERGED: reaction_configuration.bot_merged,
            PrStatus.COMMENTED: reaction_configuration.bot_commented,
        }.get(pr_info.pr.status):
            emoji_react(
                client,
                channel_id=channel_summary.channel.id,
                timestamp=pr_info.message.ts,
                emoji=emoji,
            )
            messages_reacted.add(message_key)


################################################################################
# Orchestration
################################################################################


def process_slack_message(
    channel_id: str,
    msg: dict,
    seen_pr_urls: set[str],
    github_client: GithubRequestClient | None = None,
):
    # Ignore messages the bot previously sent (or similar bots)
    if msg.get("text", "").startswith(AUTOMATION_MESSAGE_PREFIX):
        return []

    pr_matches = re.findall(PR_URL_PATTERN, msg.get("text", ""))
    potential_pr_urls = set(
        f"https://github.com/{owner}/{repo}/pull/{pr_num}"
        for owner, repo, pr_num in pr_matches
    )

    message = ProcessedSlackMessage(
        # Normalize PR URLs, and filter out any that have previously been seen.
        # We want the bot to handle each PR only once (per channel), and assume
        # that:
        # * process_slack_message is being called for messages in order (so we
        #   will _not_ skip on the _first_ occurrence of a PR)
        # * seen_pr_urls is properly scoped to this channel
        pr_urls=frozenset(potential_pr_urls - seen_pr_urls),
        reactions=frozenset(reaction["name"] for reaction in msg.get("reactions", [])),
        message_has_multiple_prs=len(potential_pr_urls) > 1,
        ts=msg["ts"],
        channel_id=channel_id,
    )

    # Skip if there are no PR URLs
    if not message.pr_urls:
        return []

    result_pr_infos: list[PrSlackInfo] = []

    # Check all PR statuses in this message
    for pr_url in message.pr_urls:
        if pr_url in seen_pr_urls:
            continue
        try:
            pr_info = check_pr_status(pr_url, github_client=github_client)
        except Exception as e:
            logger.warning(
                f"Gracefully continuing past error checking PR status for {pr_url}: {e}",
                exc_info=True,
            )
            continue

        result_pr_infos.append(
            PrSlackInfo(
                pr=pr_info,
                message=message,
            )
        )

    return result_pr_infos


def triage(
    slack_client: SlackClientInterface,
    reaction_configuration: ReactionConfiguration,
    slack_subdomain: str,
    channel_ids: list[str],
    days: int,
    allow_channel_messages: bool,
    allow_reactions: bool,
    summary_dm_user_id: list[str],
    github_client: GithubRequestClient | None = None,
):
    since = (datetime.now() - timedelta(days=days)).timestamp()
    now = datetime.now().timestamp()

    # Load info for each target channel
    channels = []
    for channel_id in channel_ids:
        channels.append(
            ChannelInfo(
                id=channel_id,
                name_with_id_fallback=slack_client.get_channel_name_with_id_fallback(
                    channel_id=channel_id
                ),
            )
        )

    channel_summaries = []
    total_messages = 0
    for channel in channels:
        logger.info(f"Processing #{channel.name_with_id_fallback} ({channel.id})...")
        messages = slack_client.conversation_history(
            channel_id=channel.id,
            oldest=str(since),
        )
        total_messages += len(messages)

        pr_infos_for_channel: list[PrSlackInfo] = []
        seen_urls_for_channel: set[str] = set()
        for msg in messages:
            new_pr_infos = process_slack_message(
                channel.id,
                msg,
                seen_urls_for_channel,
                github_client=github_client,
            )
            seen_urls_for_channel.update(pr_info.pr.url for pr_info in new_pr_infos)
            pr_infos_for_channel.extend(new_pr_infos)

        channel_summaries.append(
            ChannelSummary(channel=channel, pr_infos=tuple(pr_infos_for_channel))
        )

    send_dm_message(
        client=slack_client,
        slack_subdomain=slack_subdomain,
        reaction_configuration=reaction_configuration,
        channel_summaries=channel_summaries,
        start_time=since,
        end_time=now,
        user_ids=list(summary_dm_user_id),
    )

    # Send channel-specific reactions and summaries
    for summary in channel_summaries:
        if allow_reactions:
            react_to_pr_infos(slack_client, summary, reaction_configuration)

        send_channel_message(
            client=slack_client,
            slack_subdomain=slack_subdomain,
            reaction_configuration=reaction_configuration,
            summary=summary,
            start_time=since,
            end_time=now,
            suppress_message=not allow_channel_messages,
        )

    logger.info(f"Found {total_messages} messages across {len(channels)} channels")
