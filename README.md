# xPost — autonomous X posting agent

An always-learning X/Twitter posting agent powered by **Hermes Agent** (Nous
Research). It posts via the official X API, learns from its own engagement via
a private profile scraper, and adapts volume to the day's trends.
## Structure

```
xPost/
├── .hermes/                 # Hermes home (HERMES_HOME) — tracked selectively
│   ├── config.yaml          # Hermes configuration (no secrets)
│   └── skills/
│       ├── x-post/          # publish tweets (delegates to bundled xurl skill)
│       └── x-engagement/    # scrape own-profile engagement + learn from it
├── tools/
│   └── x_engagement.py      # twscrape-based own-profile scraper (no official API)
├── memory.json              # topics + posted history (fallback for agent.py)
├── agent.py                 # legacy standalone script (kept as fallback/dry-run)
```

Hermes framework code lives in `~/.hermes/hermes-agent` (upstream clone, like
node_modules — already on GitHub, not committed). This repo holds everything
you own.

## Setup

```bash
git clone https://github.com/You/xPost
cd xPost
echo 'export HERMES_HOME="$HOME/Projects/xPost/.hermes"' >> ~/.bashrc   # adjust path
source ~/.bashrc

# model provider + Telegram
hermes setup                       # or: hermes model / hermes gateway setup

# X posting (official API via xurl) — one-time, outside the agent:
xurl auth oauth2

# Engagement scraper session — one-time, interactive:
python3 -m venv .venv
.venv/bin/pip install twscrape
.venv/bin/python tools/x_engagement.py --login USERNAME PASSWORD
```

Daily scrape (Hermes runs this):
```bash
.venv/bin/python tools/x_engagement.py --fetch --handle USERNAME --limit 20
```

## How it learns

1. `x-engagement` fetches your last ~20 posts + replies (own profile only).
2. Hermes reasons over top vs bottom posts, reply sentiment, engagement trend.
3. Findings are written to Hermes persistent memory and applied when the
   `x-post` skill drafts the next tweets.

## Scheduling the daily window

Hermes has built-in cron. Goal: 2 posts on lean days, 3-4 when a real trend
fits. Every post goes through the **Telegram approval gate** — Hermes drafts,
sends to you, revises per your reply, and only posts what you approve.

Example jobs:

```bash
hermes cron add "0 8 * * *" "Morning: draft today's 1-2 tweets (x-post), send drafts for approval on Telegram, wait."
hermes cron add "30 9,10,11 * * *" "Check-in: if today is trending, draft 1 more and send for approval (cap 4 total); else hold."
hermes cron add "0 13 * * *" "Run x-engagement review, save learnings to memory."
```

Use `/hermes ask` or just reply in Telegram to steer topics anytime
("tomorrow: compare Fable 5 and Astra 6"). Standing instructions are saved to
memory and take priority over trending picks in the morning draft.

Same steps work on a VPS; the agent runs even when the laptop is off.

## Notes

- Posting rule enforced in the x-post skill: **no URLs** in tweets (X charges
  $0.20 per post with a link vs $0.015 without).
- Engagement reads never touch the official API (it is metered) — the
  scraper uses your session only. Scraping X is ToS-gray: keep it to your own
  profile at low volume.
- Secrets live in `.hermes/.env` and are gitignored; never commit them.