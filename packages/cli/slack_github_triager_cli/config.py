import json
from enum import Enum
from pathlib import Path
from typing import Callable

import click


class ConfigKey(Enum):
    SLACK_AUTH_PREFERENCE = "slack_auth_preference"
    SUBDOMAIN = "slack_subdomain"
    D_COOKIE = "slack_d_cookie"
    SLACK_BOT_TOKEN = "slack_bot_token"
    SLACK_WEB_URL_BASE = "slack_web_url_base"
    REACTION_APPROVAL_FROM_BOT = "reaction_approval_from_bot_emoji"
    REACTION_APPROVAL_RECOGNIZED_CSV = "reaction_approval_recognized_emoji_csv"
    REACTION_COMMENTED_FROM_BOT = "reaction_commented_from_bot_emoji"
    REACTION_COMMENTED_RECOGNIZED_CSV = "reaction_commented_recognized_emoji_csv"
    REACTION_MERGED_FROM_BOT = "reaction_merged_from_bot_emoji"
    REACTION_MERGED_RECOGNIZED_CSV = "reaction_merged_recognized_emoji_csv"
    REACTION_CLOSED_FROM_BOT = "reaction_closed_from_bot_emoji"
    REACTION_CLOSED_RECOGNIZED_CSV = "reaction_closed_recognized_emoji_csv"
    REACTION_CONFUSED_FROM_BOT = "reaction_confused_from_bot_emoji"
    GITHUB_AUTH_PREFERENCE = "github_auth_preference"
    GITHUB_APP_ID = "github_app_id"
    GITHUB_APP_PRIVATE_KEY = "github_app_private_key"
    GITHUB_TARGET_ORG = "github_target_org"

    @classmethod
    def required_keys(cls) -> list["ConfigKey"]:
        return [
            key
            for key in cls
            if key not in {ConfigKey.D_COOKIE, ConfigKey.SLACK_BOT_TOKEN}
        ]


class SlackAuthPreference(Enum):
    BOT = "bot"
    USER = "user"


class GithubAuthPreference(Enum):
    APP = "app"
    GH = "gh"


class ConfigManager:
    def __init__(self, filename: str = "secret_config.json") -> None:
        self.file_path: Path = Path(filename)
        self.data: dict[str, any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load data from the JSON config file."""
        if self.file_path.exists():
            with self.file_path.open("r") as file:
                try:
                    self.data = json.load(file)
                except json.JSONDecodeError:
                    raise ValueError(
                        f"The config file {self.file_path} contains invalid JSON."
                    )

    def _save_config(self) -> None:
        """Save data to the JSON config file."""
        with self.file_path.open("w") as file:
            json.dump(self.data, file, indent=4)

    def is_configured(self) -> bool:
        """Check if the config file has all the required keys."""
        if not all(key.value in self.data for key in ConfigKey.required_keys()):
            return False

        match self.get(ConfigKey.SLACK_AUTH_PREFERENCE):
            case SlackAuthPreference.BOT.value:
                if not self.get(ConfigKey.SLACK_BOT_TOKEN, required=False):
                    return False
            case SlackAuthPreference.USER.value:
                if not self.get(ConfigKey.D_COOKIE, required=False):
                    return False

        match self.get(ConfigKey.GITHUB_AUTH_PREFERENCE):
            case GithubAuthPreference.APP.value:
                if (
                    not self.get(ConfigKey.GITHUB_APP_ID, required=False)
                    or not self.get(ConfigKey.GITHUB_APP_PRIVATE_KEY, required=False)
                    or not self.get(ConfigKey.GITHUB_TARGET_ORG, required=False)
                ):
                    return False

        return True

    def get(self, key: ConfigKey, default: any = None, required: bool = True) -> any:
        """Retrieve a value from the config. Differs from standard gets in that it errors on missing values by default."""
        value = self.data.get(key.value, default)
        if required and not value:
            raise ValueError(f"Missing required configuration key: {key}")

        return value

    def upsert(self, key: ConfigKey, value: any) -> None:
        """Update or insert a value in the config and save."""
        if key in ConfigKey:
            self.data[key.value] = value
            self._save_config()
        else:
            raise ValueError(f"Invalid configuration key: {key}")

    def delete(self, key: ConfigKey) -> None:
        """Delete a key from the config and save."""
        if key.value in self.data:
            del self.data[key.value]
            self._save_config()

    def __dict__(self) -> dict[str, any]:
        return self.data


def reload_config(
    config: ConfigManager, d_cookie_fetcher: Callable[[str], str]
) -> None:
    config.upsert(
        ConfigKey.SUBDOMAIN,
        click.prompt(
            "Slack subdomain (e.g., 'foo')",
            type=str,
            default=config.get(ConfigKey.SUBDOMAIN, required=False),
            show_default=True
            if config.get(ConfigKey.SUBDOMAIN, required=False)
            else False,
        )
        .strip()
        .lower(),
    )

    config.upsert(
        ConfigKey.REACTION_APPROVAL_FROM_BOT,
        click.prompt(
            "Reaction from the bot for approved PRs (e.g., 'white_check_mark')",
            type=str,
            default=config.get(ConfigKey.REACTION_APPROVAL_FROM_BOT, required=False),
            show_default=True
            if config.get(ConfigKey.REACTION_APPROVAL_FROM_BOT, required=False)
            else False,
        ),
    )

    config.upsert(
        ConfigKey.REACTION_APPROVAL_RECOGNIZED_CSV,
        click.prompt(
            "What reactions should the bot treat as already indicating approval? (e.g., 'white_check_mark,bufo-gives-approval,approved')",
            type=str,
            default=config.get(
                ConfigKey.REACTION_APPROVAL_RECOGNIZED_CSV, required=False
            ),
            show_default=True
            if config.get(ConfigKey.REACTION_APPROVAL_RECOGNIZED_CSV, required=False)
            else False,
        ),
    )

    config.upsert(
        ConfigKey.REACTION_COMMENTED_FROM_BOT,
        click.prompt(
            "Reaction from the bot for PRs with comments (e.g., 'speech_balloon')",
            type=str,
            default=config.get(ConfigKey.REACTION_COMMENTED_FROM_BOT, required=False),
            show_default=True
            if config.get(ConfigKey.REACTION_COMMENTED_FROM_BOT, required=False)
            else False,
        ),
    )

    config.upsert(
        ConfigKey.REACTION_COMMENTED_RECOGNIZED_CSV,
        click.prompt(
            "What reactions should the bot treat as already indicating commented? (e.g., 'speech_balloon,commented')",
            type=str,
            default=config.get(
                ConfigKey.REACTION_COMMENTED_RECOGNIZED_CSV, required=False
            ),
            show_default=True
            if config.get(ConfigKey.REACTION_COMMENTED_RECOGNIZED_CSV, required=False)
            else False,
        ),
    )

    config.upsert(
        ConfigKey.REACTION_MERGED_FROM_BOT,
        click.prompt(
            "Reaction from the bot for merged PRs (e.g., 'package')",
            type=str,
            default=config.get(ConfigKey.REACTION_MERGED_FROM_BOT, required=False),
            show_default=True
            if config.get(ConfigKey.REACTION_MERGED_FROM_BOT, required=False)
            else False,
        ),
    )

    config.upsert(
        ConfigKey.REACTION_MERGED_RECOGNIZED_CSV,
        click.prompt(
            "What reactions should the bot treat as already indicating merged? (e.g., 'package,merged')",
            type=str,
            default=config.get(
                ConfigKey.REACTION_MERGED_RECOGNIZED_CSV, required=False
            ),
            show_default=True
            if config.get(ConfigKey.REACTION_MERGED_RECOGNIZED_CSV, required=False)
            else False,
        ),
    )

    config.upsert(
        ConfigKey.REACTION_CONFUSED_FROM_BOT,
        click.prompt(
            "Reaction from the bot for messages with multiple PRs (e.g., 'robot_face')",
            type=str,
            default=config.get(ConfigKey.REACTION_CONFUSED_FROM_BOT, required=False),
            show_default=True
            if config.get(ConfigKey.REACTION_CONFUSED_FROM_BOT, required=False)
            else False,
        ),
    )

    config.upsert(
        ConfigKey.SLACK_AUTH_PREFERENCE,
        click.prompt(
            "Do you prefer to use a Slack bot token or a Slack user token?",
            type=click.Choice(
                [SlackAuthPreference.BOT.value, SlackAuthPreference.USER.value]
            ),
            default=config.get(ConfigKey.SLACK_AUTH_PREFERENCE, required=False),
            show_default=True
            if config.get(ConfigKey.SLACK_AUTH_PREFERENCE, required=False)
            else False,
        ),
    )

    match config.get(ConfigKey.SLACK_AUTH_PREFERENCE):
        case SlackAuthPreference.BOT.value:
            current_bot_token = config.get(ConfigKey.SLACK_BOT_TOKEN, required=False)
            if not current_bot_token or click.confirm("Provide new Slack bot token?"):
                config.upsert(
                    ConfigKey.SLACK_BOT_TOKEN,
                    click.prompt(
                        f"Provide your bot token{' (press enter to keep existing)' if current_bot_token else ''}",
                        type=str,
                        default=config.get(ConfigKey.SLACK_BOT_TOKEN, required=False),
                        show_default=False,
                    ),
                )

            if config.get(ConfigKey.D_COOKIE, required=False) and click.confirm(
                "Clear your user auth token?"
            ):
                config.delete(ConfigKey.D_COOKIE)

        case SlackAuthPreference.USER.value:
            if not config.get(ConfigKey.D_COOKIE, required=False) or click.confirm(
                "Re-authenticate to Slack?"
            ):
                click.echo(
                    "Next we'll open a browser window. Log in to slack, and this script will capture your session cookie."
                )
                click.confirm("Enter y to continue...", abort=True)
                config.upsert(
                    ConfigKey.D_COOKIE,
                    d_cookie_fetcher(config.get(ConfigKey.SUBDOMAIN)),
                )

            if config.get(ConfigKey.SLACK_BOT_TOKEN, required=False) and click.confirm(
                "Clear your bot auth token?"
            ):
                config.delete(ConfigKey.SLACK_BOT_TOKEN)

            click.echo("Configuration saved!\n")

    config.upsert(
        ConfigKey.GITHUB_AUTH_PREFERENCE,
        click.prompt(
            "Do you prefer to use a GitHub app or the gh CLI?",
            type=click.Choice(
                [GithubAuthPreference.APP.value, GithubAuthPreference.GH.value]
            ),
            default=config.get(ConfigKey.GITHUB_AUTH_PREFERENCE, required=False),
            show_default=True
            if config.get(ConfigKey.GITHUB_AUTH_PREFERENCE, required=False)
            else False,
        ),
    )

    match config.get(ConfigKey.GITHUB_AUTH_PREFERENCE):
        case GithubAuthPreference.APP.value:
            config.upsert(
                ConfigKey.GITHUB_TARGET_ORG,
                click.prompt(
                    "Provide your GitHub target organization",
                    type=str,
                    default=config.get(ConfigKey.GITHUB_TARGET_ORG, required=False),
                    show_default=True,
                ),
            )
            config.upsert(
                ConfigKey.GITHUB_APP_ID,
                click.prompt(
                    "Provide your GitHub app ID",
                    type=str,
                    default=config.get(ConfigKey.GITHUB_APP_ID, required=False),
                    show_default=True,
                ),
            )
            config.upsert(
                ConfigKey.GITHUB_APP_PRIVATE_KEY,
                click.prompt(
                    "Provide your GitHub app private key (or hit enter to keep existing)",
                    type=str,
                    default=config.get(
                        ConfigKey.GITHUB_APP_PRIVATE_KEY, required=False
                    ),
                    show_default=False,
                ),
            )
        case GithubAuthPreference.GH.value:
            if config.get(ConfigKey.GITHUB_APP_ID, required=False) and click.confirm(
                "Clear your GitHub app ID?"
            ):
                config.delete(ConfigKey.GITHUB_APP_ID)

            if config.get(
                ConfigKey.GITHUB_APP_PRIVATE_KEY, required=False
            ) and click.confirm("Clear your GitHub app private key?"):
                config.delete(ConfigKey.GITHUB_APP_PRIVATE_KEY)

            if config.get(
                ConfigKey.GITHUB_TARGET_ORG, required=False
            ) and click.confirm("Clear your GitHub target organization?"):
                config.delete(ConfigKey.GITHUB_TARGET_ORG)
