#!/usr/bin python

import functools
import logging
import os

import click
from slack_github_triager_core.github_client import GithubRequestClient
from slack_github_triager_core.processing import (
    ReactionConfiguration,
)
from slack_github_triager_core.processing import (
    triage as processing_triage,
)
from slack_github_triager_core.slack_client import (
    SlackRequestClient,
    get_slack_tokens,
)

from slack_github_triager_cli.browser_utils import (
    fetch_d_cookie,
)
from slack_github_triager_cli.config import (
    ConfigKey,
    ConfigManager,
    GithubAuthPreference,
    SlackAuthPreference,
    reload_config,
)

################################################################################
# Configuration
################################################################################
CONFIG = ConfigManager()


################################################################################
# Helpers
################################################################################
@functools.lru_cache()
def get_slack_client() -> SlackRequestClient:
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


@functools.lru_cache()
def get_github_client() -> GithubRequestClient | None:
    if CONFIG.get(ConfigKey.GITHUB_AUTH_PREFERENCE) == GithubAuthPreference.APP.value:
        return GithubRequestClient(
            app_id=CONFIG.get(ConfigKey.GITHUB_APP_ID),
            private_key=CONFIG.get(ConfigKey.GITHUB_APP_PRIVATE_KEY),
            target_org=CONFIG.get(ConfigKey.GITHUB_TARGET_ORG),
        )
    return None


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
COLORS = {
    "WARNING": "\033[93m",  # Yellow
    "ERROR": "\033[91m",  # Red
    "CRITICAL": "\033[95m",  # Magenta
    "DEBUG": "\033[90m",  # Gray
    "RESET": "\033[0m",  # Reset
}


class ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        color = COLORS.get(record.levelname, "")
        formatted = super().format(record)
        if color:
            return f"{color}{formatted}{COLORS['RESET']}"
        return formatted


@click.group()
def cli():
    handler = logging.StreamHandler()
    handler.setFormatter(ColorFormatter("%(message)s"))
    logging.basicConfig(
        level=logging.DEBUG if os.getenv("DEBUG") else logging.INFO, handlers=[handler]
    )


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
    processing_triage(
        slack_client=get_slack_client(),
        github_client=get_github_client(),
        slack_subdomain=CONFIG.get(ConfigKey.SUBDOMAIN),
        reaction_configuration=ReactionConfiguration(
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
        ),
        channel_ids=channel_ids,
        days=days,
        allow_channel_messages=allow_channel_messages,
        allow_reactions=allow_reactions,
        summary_dm_user_id=summary_dm_user_id,
    )


if __name__ == "__main__":
    cli()
