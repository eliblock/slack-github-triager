import json
from enum import Enum
from pathlib import Path
from typing import Callable

import click


class ConfigKey(Enum):
    SUBDOMAIN = "slack_subdomain"
    D_COOKIE = "slack_d_cookie"
    SLACK_WEB_URL_BASE = "slack_web_url_base"
    REACTION_APPROVAL_FROM_BOT = "reaction_approval_from_bot_emoji"
    REACTION_APPROVAL_RECOGNIZED_CSV = "reaction_approval_recognized_emoji_csv"
    REACTION_COMMENTED_FROM_BOT = "reaction_commented_from_bot_emoji"
    REACTION_COMMENTED_RECOGNIZED_CSV = "reaction_commented_recognized_emoji_csv"
    REACTION_MERGED_FROM_BOT = "reaction_merged_from_bot_emoji"
    REACTION_MERGED_RECOGNIZED_CSV = "reaction_merged_recognized_emoji_csv"
    REACTION_CONFUSED_FROM_BOT = "reaction_confused_from_bot_emoji"


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
        if not all(key.value in self.data for key in ConfigKey):
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

    if not config.get(ConfigKey.D_COOKIE, required=False) or click.confirm(
        "Re-authenticate to Slack?"
    ):
        click.echo(
            "Next we'll open a browser window. Log in to slack, and this script will capture your session cookie."
        )
        click.confirm("Enter y to continue...", abort=True)
        config.upsert(
            ConfigKey.D_COOKIE, d_cookie_fetcher(config.get(ConfigKey.SUBDOMAIN))
        )

    click.echo("Configuration saved!\n")
