# CMA

Type `/cma` plus an address in the grokbot Slack channel and get 4–5 nearby comps: homes sold in the last 12 months and homes on the market now, all within **1 mile**.

```text
/cma428 Lawnview Ave, New Castle, Pennsylvania 16105
```

A space or colon also works: `/cma 428 Lawnview Ave, New Castle, PA 16105`.

The reply includes the subject’s beds, baths, and square footage when a listing or the public assessment record has them, a value band from the sold comps, and the closest-matching mix of about 3 sales and 2 active listings. It is a comp set, not an appraisal.

## Try it locally

```bash
PYTHONPATH=src python -m cma "/cma428 Lawnview Ave, New Castle, Pennsylvania 16105"
```

`--json` prints the same report as JSON.

```bash
PYTHONPATH=src python -m unittest tests.test_cma
```

## Grok Bot

The skill in `.grok/skills/cma/SKILL.md` is the command the bot should follow. In the grokbot Slack channel, a routine like this keeps it narrow:

> When a message in this channel starts with `/cma`, run `PYTHONPATH=src python -m cma` in the cma repo with the full message and post the command’s stdout in the thread. Do not add comps that the command did not return.

## Slack app

A Socket Mode bot answers the same command without an LLM in the middle. Create a Slack app, turn on Socket Mode, and create an app-level token with the `connections:write` scope. Subscribe to the `message.channels` event (and `message.groups` if the grokbot channel is private). Add the bot token scopes `chat:write`, `channels:history`, and `groups:history`. Invite the app to the grokbot channel.

```bash
pip install -e ".[slack]"
cp .env.example .env
# fill in SLACK_BOT_TOKEN (xoxb-) and SLACK_APP_TOKEN (xapp-)
# optional: CMA_SLACK_CHANNEL_ID so it only answers in that channel
python -m cma.slack_bot
```

A registered slash command `/cma` is also accepted. The address is the command text. The glued form `/cma428 ...` is a channel message, which is what the grokbot channel uses.

## Where the numbers come from

- The Census geocoder turns the address into a map point and ZIP.
- Redfin’s public map search supplies active listings and sales from the last 12 months. Homes farther than 1 mile are dropped.
- In Lawrence County, PA (161xx), the county assessment map fills in beds, baths, square footage, and year built when the home is not listed. Assessed value is not used as a price. Owner names are not shown.
