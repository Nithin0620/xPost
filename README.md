# xPost

An autonomous X (Twitter) posting agent that drafts tweets in your voice, gets
your approval on Telegram, publishes via the official X API (`xurl`), and learns
from how your own posts perform.

Built on [Hermes Agent](https://github.com/NousResearch/Hermes-Agent) with Gemini
as the model.

## How it works

```
 research + memory ──► draft (x-post skill) ──► Telegram review ──► xurl post
        ▲                                         (you approve)          │
        └──── lessons ◄── x-engagement skill ◄── scrape own profile ◄────┘
```

| Piece | What it does |
|---|---|
| `.hermes/skills/x-post/SKILL.md` | Daily drafting + **mandatory Telegram approval gate** + posting rules (no links, ≤260 chars, no repeats, 0–2 hashtags). |
| `.hermes/skills/x-engagement/SKILL.md` | Scrapes your own profile's metrics/replies and writes "what works / what doesn't" to memory. |
| `tools/x_engagement.py` | Read-only own-profile scraper (twscrape). |
| `tools/x_db.py` | Stores drafts, published posts and engagement snapshots in MongoDB (falls back to `data/*.jsonl`). |
| `agent.py` | Standalone one-shot poster (no approval gate) — Gemini draft → `xurl post`. Use `--dry-run` to preview. |

**Posting only ever goes through `xurl`** (official X API v2). Plain-text posts
are cheap; posts with URLs cost much more, so the agent never includes links.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # fill in GEMINI_API_KEY, Telegram, X client id/secret, MONGODB_URI
```

1. **Posting auth (xurl)** — install [xurl](https://github.com/xdevplatform/xurl),
   then run once, outside the agent: `xurl auth oauth2`.
2. **Scraper auth (twscrape)** — export cookies from a logged-in x.com browser
   session to `auth/x_cookies.json` (gitignored — never commit it), then:
   ```bash
   .venv/bin/python tools/x_engagement.py --cookies auth/x_cookies.json --cookies-username <handle>
   ```
3. **Hermes** — run Hermes from the repo root so it picks up `.hermes/config.yaml`
   and the skills; enable the Telegram gateway with your bot token and home channel.

## Commands

```bash
.venv/bin/python tools/x_engagement.py --fetch --handle <handle> --limit 20   # scrape + top/bottom summary
.venv/bin/python tools/x_db.py list-posts --status published --limit 10      # post history
.venv/bin/python agent.py --dry-run                                          # preview a Gemini draft
.venv/bin/python agent.py --selfcheck
```

## Security

- `.env`, `auth/`, `accounts.db` and `data/` are gitignored. Never commit cookies
  or tokens — an `auth_token` cookie is a full login to your account.
- If a cookie file was ever pushed, log out all sessions in X → Settings →
  Security → Sessions to invalidate it.
