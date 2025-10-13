# slack-github-triager-core

Reads Slack messages in channels, identifies GitHub PR links, checks their status, and optionally reacts or sends summaries.

## Installation

```bash
uv add slack-github-triager-core
```

## Usage

```python
from slack_github_triager_core.slack_client import SlackRequestClient, get_slack_tokens
from slack_github_triager_core.processing import triage, ReactionConfiguration
from slack_github_triager_core.github_client import GithubRequestClient


# Create a slack client either by implementing SlackClientInterface yourself...
class MySlackClient(SlackClientInterface):
    @override
    def get_channel_name_with_id_fallback(self, *, channel_id: str) -> str:
        ...
    @override
    def open_dm(self, *, user_id: str) -> str:
        ...
    ...
client = MySlackClient()
# ...or by using the built-in implementation with SlackClient. To use
# SlackClient either create its underlying SlackRequestClient with a bot token...
client = SlackClient(
    slack_client=SlackRequestClient(
      subdomain="your-workspace",
      token="xoxb-your-bot-token",
      enterprise_token="",
      cookie="",
      use_bot=True,
  )
)
# ...or with user session (requires d_cookie from browser)
token, enterprise_token = get_slack_tokens(
    subdomain="your-workspace",
    d_cookie="your-d-cookie-from-browser"
)
client = SlackClient(
    SlackRequestClient(
      subdomain="your-workspace",
      token=token,
      enterprise_token=enterprise_token,
      cookie="your-d-cookie-from-browser",
      use_bot=False,
  )
)

# Configure reaction emojis for PR status
reaction_config = ReactionConfiguration(
    bot_approved="white_check_mark",
    bot_considers_approved={"approved", "lgtm", "ship-it"},
    bot_commented="speech_balloon",
    bot_considers_commented={"commented", "feedback"},
    bot_merged="merged",
    bot_considers_merged={"merged", "shipit"},
    bot_confused="thinking_face",
)

# Optional: Create GitHub client for API access instead of gh CLI
github_client = GithubRequestClient(
    app_id="123456",
    private_key="""-----BEGIN PRIVATE KEY-----
YOUR_PRIVATE_KEY_HERE
-----END PRIVATE KEY-----""",
    target_org="your-org",
)

# Run triage on channels
triage(
    client=client,
    slack_subdomain="your-workspace",
    reaction_configuration=reaction_config,
    channel_ids=("C1234567890", "C0987654321"),
    days=7,
    allow_channel_messages=True,
    allow_reactions=True,
    summary_dm_user_id=("U1234567890",),
    github_client=github_client,  # Optional: omit to use gh CLI
)
```

This will:
- Scan the last 7 days of messages in the specified channels
- Find GitHub PR links and check their status (using GitHub API if `github_client` provided, otherwise `gh` CLI)
- React to messages with appropriate emojis based on PR status
- Send summary DMs to specified users with PRs needing attention

## GitHub Access Methods

The library supports two methods for accessing GitHub:

1. **GitHub CLI** (default): Uses the `gh` command-line tool with your existing authentication
2. **GitHub App** (optional): Uses GitHub App credentials for API access with higher rate limits

To use GitHub App authentication, create a GitHub App with **Pull requests (read only)** permission and provide the client as shown above.
