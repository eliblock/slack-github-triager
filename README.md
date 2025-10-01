# slack-github-triager

`slack-github-triager` reads slack messages in a targetted slack channel and
identifies links to PRs. When it finds them, it uses `gh` to check the current
status of the PRs, and (optionally...):
* reacts to the slack message with the PR's status
* sends a summary message of all PRs which are pending attention to the channel
* DMs users a summary of all PRs which are pending attention across all scanned
channels

## ⚠️ avoid Slack account takeovers

When you configure this tool, it fetches a potentially long-lived slack session
cookie and stores it in a file in this directory called `secret_config.json`.
Anyone with access to that cookie may interact with Slack on your behalf.

If you lose control of the file containing that cookie, or if someone else gains
access to it, [sign out of all Slack sessions](https://slack.com/help/articles/214613347-Sign-out-of-Slack)
immediately.

## Setup
```sh
# First, clone the repo. Then...

# Setup your environment
brew install chromedriver --cask
brew install gh
uv sync

# Configure gh
gh auth login

# Configure the tool
uv run triager configure # follow the prompts
uv run triager hey # should greet you by name

# Triage!
# fill in CHANNEL_ID with a slack channel id (e.g., C06F2NQW827) - you may use multiple
# fill in USER_ID with a user who should get a summary DM - this option may be passed multiple times
uv run triager triage CHANNEL_ID --allow-reactions --allow-channel-messages --summary-dm-user-id USER_ID
```

No guarantee of CLI-command level stability is offered between various commits
to this tool.

## set up `cron`

This tool can be run in a cron to auto-sort your channels every few minutes.
**Before setting up a cron, ensure the script is configured (above) and run it
at least once locally.** To test your setup, run:

```sh
bin/run-in-uv.sh triage CHANNEL_ID --allow-reactions --allow-channel-messages --summary-dm-user-id USER_ID
```

...if you see a successful output, you may proceed.

To configure the cron, edit your crontab file (`crontab -e`) to include an entry
like:

```txt
*/5 * * * * <absolute-path-to-this-repo>/bin/run-in-uv.sh triage CHANNEL_ID --allow-reactions --allow-channel-messages --summary-dm-user-id USER_ID >>~/cron-stdout.log 2>>~/cron-stderr.log
```
