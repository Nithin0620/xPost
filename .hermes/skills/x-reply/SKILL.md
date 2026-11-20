---
name: x-reply
description: "Draft replies to comments on the owner's OWN recent X posts, in the owner's voice, with the same Telegram approval gate as x-post. Posts approved replies via xurl only."
version: 1.0.0
author: nithin
license: MIT
platforms: [linux]
prerequisites:
  commands: [xurl, python3]
metadata:
  hermes:
    tags: [twitter, x, social-media, replies, human-in-the-loop]
    homepage: https://github.com/NousResearch/Hermes-Agent
---

# x-reply — answer people who replied to the owner

Real accounts talk back. This skill finds replies on the owner's recent posts
that haven't been answered yet, drafts short human replies, and publishes only
what the owner approves.

## Scope (MANDATORY)
- Only reply to people who replied to the **owner's own posts**. Never cold-reply
  to strangers' tweets, never mass-reply, never like/follow in bulk.
- Max 5 reply drafts per run, max 2 runs per day.
- Same approval gate as x-post: **never call xurl until the owner approved the
  exact reply text on Telegram.**

## Workflow

1. Refresh data, then list unanswered replies from the last 3 days:
   ```bash
   .venv/bin/python tools/x_engagement.py --fetch --handle "$X_HANDLE" --limit 10
   .venv/bin/python tools/x_engagement.py --pending-replies --handle "$X_HANDLE"
   ```
2. Pick replies worth answering: genuine questions, disagreement with a point,
   useful additions. Skip spam, bots, one-word reactions, and anything hostile.
3. Draft each reply following `../x-post/VOICE.md`. Replies are even shorter and
   more casual than posts: answer the question directly, one or two sentences,
   no "Great question!", no thanking-for-engagement filler.
4. Lint every draft and rewrite until it passes:
   ```bash
   .venv/bin/python tools/x_style.py check "<reply text>"
   ```
5. Send to Telegram and STOP until the owner answers:
   ```
   Reply drafts:

   1) @author on "<post snippet>": "<their reply>"
      -> <your draft>

   Approve 1, 2, all, none — or tell me what to change.
   ```
6. For each approved reply, publish with xurl (the only posting path):
   ```bash
   xurl -X POST /2/tweets -d '{"text":"<reply text>","reply":{"in_reply_to_tweet_id":"<reply id>"}}'
   ```
   Then log it so it's never answered twice:
   ```bash
   .venv/bin/python tools/x_db.py save-post --status published \
     --payload '{"id":"<new tweet id>","text":"<reply text>","in_reply_to":"<reply id>"}'
   ```
7. If the owner edited a draft, record it with `tools/x_db.py save-edit` (see x-post Phase 3).

## Failure handling
- 429: wait 5+ minutes, retry once, else defer. 401/403: owner re-runs `xurl auth oauth2`.
- Scraper auth expired: tell the owner to re-inject cookies (see x-engagement); never type credentials.
