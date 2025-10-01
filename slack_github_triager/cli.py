#!/usr/bin python

import functools
from datetime import datetime, timedelta

import click

from slack_github_triager.config import (
    ConfigKey,
    ConfigManager,
    SlackAuthPreference,
    reload_config,
)
from slack_github_triager.processing import (
    ChannelInfo,
    ChannelSummary,
    PrSlackInfo,
    ReactionConfiguration,
    process_slack_message,
    react_to_pr_infos,
    send_channel_message,
    send_dm_message,
)
from slack_github_triager.slack_client import (
    SlackRequestClient,
    SlackRequestError,
    fetch_d_cookie,
    get_slack_tokens,
)

################################################################################
# Configuration
################################################################################
CONFIG = ConfigManager()


################################################################################
# Helpers
################################################################################
@functools.lru_cache()
def get_slack_client() -> "SlackRequestClient":
    match CONFIG.get(ConfigKey.SLACK_AUTH_PREFERENCE):
        case SlackAuthPreference.BOT.value:
            return SlackRequestClient(
                subdomain=CONFIG.get(ConfigKey.SUBDOMAIN),
                token=CONFIG.get(ConfigKey.SLACK_BOT_TOKEN),
                enterprise_token="",
                cookie="",
                use_bot=True,
            )
        case SlackAuthPreference.USER.value:
            token, enterprise_token = get_slack_tokens(
                subdomain=CONFIG.get(ConfigKey.SUBDOMAIN),
                d_cookie=CONFIG.get(ConfigKey.D_COOKIE),
            )
            return SlackRequestClient(
                subdomain=CONFIG.get(ConfigKey.SUBDOMAIN),
                token=token,
                enterprise_token=enterprise_token,
                cookie=CONFIG.get(ConfigKey.D_COOKIE),
                use_bot=False,
            )
        case _:
            raise ValueError(
                f"Invalid slack auth preference: {CONFIG.get(ConfigKey.SLACK_AUTH_PREFERENCE)}"
            )


def ensure_configured(cmd):
    @functools.wraps(cmd)
    def wrapper(*args, **kwargs):
        ctx = click.get_current_context()
        if not CONFIG.is_configured():
            click.echo("Configuration not found. Attempting to re-configure...")
            reload_config(config=CONFIG, d_cookie_fetcher=fetch_d_cookie)
        return ctx.invoke(cmd, *args, **kwargs)

    return wrapper


################################################################################
# CLI
################################################################################
@click.group()
def cli():
    pass


@cli.command()
def configure():
    reload_config(config=CONFIG, d_cookie_fetcher=fetch_d_cookie)


@cli.command()
@ensure_configured
def hey():
    client = get_slack_client()
    match CONFIG.get(ConfigKey.SLACK_AUTH_PREFERENCE):
        case SlackAuthPreference.BOT.value:
            auth_info = client.get("/api/auth.test")
            click.echo(f"Hello {auth_info['user']}")
        case SlackAuthPreference.USER.value:
            profile = client.get("/api/users.profile.get")
            click.echo(
                f"Hello {profile['profile']['display_name_normalized']} ({profile['profile']['email']})"
            )


@cli.command()
@click.argument("channel-ids", type=str, required=True, nargs=-1)
@click.option("--days", type=int, default=4)
@click.option("--allow-channel-messages", is_flag=True, default=False)
@click.option("--allow-reactions", is_flag=True, default=False)
@click.option("--summary-dm-user-id", type=str, multiple=True)
@ensure_configured
def triage(
    channel_ids: tuple[str],
    days: int,
    allow_channel_messages: bool,
    allow_reactions: bool,
    summary_dm_user_id: tuple[str],
):
    client = get_slack_client()
    since = (datetime.now() - timedelta(days=days)).timestamp()
    now = datetime.now().timestamp()

    # Load info for each target channel
    channels = []
    for channel_id in channel_ids:
        try:
            channel_name = client.get(
                "/api/conversations.info", params={"channel": channel_id}
            )["channel"]["name"]
        except SlackRequestError:
            click.echo("gracefully ignoring channel failure to fetch channel name...")
            channel_name = channel_id
        channels.append(ChannelInfo(id=channel_id, name_with_id_fallback=channel_name))

    channel_summaries = []
    total_messages = 0
    for channel in channels:
        click.echo(f"Processing #{channel.name_with_id_fallback} ({channel.id})...")
        messages = client.get(
            "/api/conversations.history",
            params={"channel": channel.id, "oldest": str(since)},
        )["messages"]
        total_messages += len(messages)

        pr_infos_for_channel: list[PrSlackInfo] = []
        seen_urls_for_channel = set()
        for msg in messages:
            new_pr_infos = process_slack_message(
                client, channel.id, msg, seen_urls_for_channel
            )
            seen_urls_for_channel.update(pr_info.pr.url for pr_info in new_pr_infos)
            pr_infos_for_channel.extend(new_pr_infos)

        channel_summaries.append(
            ChannelSummary(channel=channel, pr_infos=tuple(pr_infos_for_channel))
        )

    reaction_configuration = ReactionConfiguration(
        bot_approved=CONFIG.get(ConfigKey.REACTION_APPROVAL_FROM_BOT),
        bot_considers_approved=set(
            CONFIG.get(ConfigKey.REACTION_APPROVAL_RECOGNIZED_CSV).split(",")
        ),
        bot_commented=CONFIG.get(ConfigKey.REACTION_COMMENTED_FROM_BOT),
        bot_considers_commented=set(
            CONFIG.get(ConfigKey.REACTION_COMMENTED_RECOGNIZED_CSV).split(",")
        ),
        bot_merged=CONFIG.get(ConfigKey.REACTION_MERGED_FROM_BOT),
        bot_considers_merged=set(
            CONFIG.get(ConfigKey.REACTION_MERGED_RECOGNIZED_CSV).split(",")
        ),
        bot_confused=CONFIG.get(ConfigKey.REACTION_CONFUSED_FROM_BOT),
    )

    send_dm_message(
        client=client,
        slack_subdomain=CONFIG.get(ConfigKey.SUBDOMAIN),
        reaction_configuration=reaction_configuration,
        channel_summaries=channel_summaries,
        start_time=since,
        end_time=now,
        user_ids=list(summary_dm_user_id),
    )

    # Send channel-specific reactions and summaries
    for summary in channel_summaries:
        if allow_reactions:
            react_to_pr_infos(client, summary, reaction_configuration)

        send_channel_message(
            client=client,
            slack_subdomain=CONFIG.get(ConfigKey.SUBDOMAIN),
            reaction_configuration=reaction_configuration,
            summary=summary,
            start_time=since,
            end_time=now,
            suppress_message=not allow_channel_messages,
        )

    click.echo(f"Found {total_messages} messages across {len(channels)} channels")


if __name__ == "__main__":
    cli()
