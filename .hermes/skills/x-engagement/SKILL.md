---
name: x-engagement
description: "Scrape the owner's OWN X profile (no official API) for recent posts, engagement metrics, and replies; analyze what worked / fell flat; learn from it and persist the strategy."
version: 1.0.0
author: nithin
license: MIT
platforms: [linux]
prerequisites:
  commands: [python3]
metadata:
  hermes:
    tags: [twitter, x, social-media, engagement, learning]
    homepage: https://github.com/NousResearch/Hermes-Agent
---

# x-engagement — learn from the owner's own post performance

Reads the owner's engagement WITHOUT the official X API. Uses a session-keyed
scraper (`tools/x_engagement.py`, twscrape) that pulls only the owner's own
profile. Never read anyone else's profile. Never use the official read API
for this — that is metered.

## When to run

- Once at the start of the daily posting window (warm-up: learn from last
  day), and once at the end (review what today's posts did).
- Keep it lightweight: last 10-20 posts, top 5 replies each.

## Commands

```bash
# one-time setup (user runs interactively, outside agent):
cd /home/nithin/Projects/xPost
.venv/bin/python tools/x_engagement.py --login USERNAME PASSWORD

# daily fetch + summary:
cd /home/nithin/Projects/xPost
.venv/bin/python tools/x_engagement.py --fetch --handle USERNAME --limit 20
```

The script prints the top 3 and bottom 3 posts by engagement score along with
sample replies. Read that output.

## Analysis job (the actual learning)

After every fetch, reason over the data and then WRITE the findings to
persistent memory so future posts improve:

1. **Pattern mining:** compare top vs bottom posts. What differed? Topic area,
   question vs statement, length, emoji/hashtag use, time of day, hook style.
2. **Replies:** what did commenters ask or react to? Complaints, praise, or
   interests worth following up on.
3. **Trend of engagement:** is the account's engagement rising or falling vs
   recent past? If falling, hypothesize why (voice drift, topics, posting
   noise) before recommending changes.
4. **Persist:** write a crisp "what works / what doesn't" note to memory.
   Keep it short (a few bullets). Delete outdated advice when it contradicts
   newer data — never let stale winners crowd out current data.
5. Apply the findings when generating today's tweets (see x-post skill).

## Guardrails

- Do NOT export / save any other user's posts or data — owner profile only.
- Do NOT store X credentials anywhere but the twscrape session store
  (`accounts.db`). Never print them.
- If the scraper fails auth (session expired), tell the user to re-run the
  `--login` step outside the agent; never try to infer or type credentials.
- Keep data consumption low: on the owner's own profile, the scrape is tiny.