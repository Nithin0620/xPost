---
name: x-post
description: "Post to X/Twitter as the owner, cheaply and safely. Drafts tweets with a HUMAN APPROVAL GATE on Telegram: never publishes without the owner's review and approval."
version: 1.1.0
author: nithin
license: MIT
platforms: [linux]
prerequisites:
  commands: [xurl]
metadata:
  hermes:
    tags: [twitter, x, social-media, posting, human-in-the-loop]
    homepage: https://github.com/NousResearch/Hermes-Agent
---

# x-post — publish tweets with the owner's approval

Posts to the owner's X account using the bundled **xurl** skill (official X
API v2). Never build your own posting path — `xurl` already exists.

## THE APPROVAL GATE (MANDATORY, most important rule in this skill)

**Never call `xurl post` until the owner has explicitly reviewed and approved
the exact tweet text in Telegram.**

- Posting without Telegram approval is a hard violation. There is no
  exception, not even when the daily window is about to close.
- If Telegram/replies are unavailable, do NOT post. Defer and report.

## Posting rules (MANDATORY)

1. **Never post links/URLs.** A tweet containing a URL costs $0.20 on X
   (plain text costs $0.015). Mention repos/products by name, never by URL.
2. **Max 260 characters.** X allows 280; leave headroom for safety.
3. **No repeats.** Search memory and past engagement data first. Never post a
   tweet whose idea/topic was already posted in the last 14 days.
4. **Quality over volume.** User wants 2 posts on lean days, 3-4 on strong
   trending days. Never post filler just to hit a number.
5. **No hashtag spam.** 0-2 hashtags max.
6. **Volume decision:** use the day's trending/news research. If a real trend
   fits the account's voice -> post 3-4; otherwise keep it at 2.

## Standing instructions ("senior enhancer")

The owner may give direction anytime on Telegram, e.g.:

- "tomorrow's post should talk about Astra 6"
- "compare Fable 5 and Astra 6 in the next post"
- "don't pitch, be opinionated" / "always end with a take"

These become STANDING RULES:
1. Save the instruction to persistent memory immediately when given.
2. Check memory BEFORE drafting every day — standing instructions always
   override topic selection. A requested topic ("Astra 6") takes priority over
   trending/news picks.
3. Bring the owner's reviewed feedback into EVERY future draft without them
   having to repeat it.

## Workflow

### Phase 1 — Gather and draft
1. Check persistent memory for: standing instructions, review style feedback,
   voice, posted history.
2. If a standing instruction names a repo ("talk about my repo X"), fetch its
   current description + recent commits so the draft is accurate:
   ```bash
   curl -s "https://api.github.com/repos/USER/REPO"        # description, stars, language
   curl -s "https://api.github.com/repos/USER/REPO/events" # recent activity
   ```
   Use the real data — never invent repo details.
3. Run engagement scrape (`tools/x_engagement.py --fetch`), read top/bottom
   posts to apply what worked.
4. Research today's trends/news (web search).
5. Draft 1-2 candidate tweets. For each, include WHY you chose it (trend
   signal, requested topic/repo, or past-performance pattern).

### Phase 2 — Send for review (Telegram)
Send to the owner in Telegram:
```
Ready to post. Drafts:

1) <tweet text>
   why: trending topic fits voice / you asked for Astra 6 / pattern that got N likes

2) <tweet text>
   why: ...

Approve 1, 2, both, none — or tell me what to change.
```
Then STOP and wait for the reply. Do not post, do not draft more until
the owner answers.

### Phase 3 — Revise loop
On the owner's reply:
- **Approve (all / one)**: only the explicitly approved tweet(s) proceed.
- **Feedback**: revise exactly per the feedback; resend revised drafts for a
  new approval. You may iterate up to 3 times; after that, ask if they want a
  fresh angle instead of endlessly rewording.
- **Kill / hold**: drop that tweet, do not post it.
- **New instruction**: save it to memory as standing direction, re-draft,
  resend for approval.

### Phase 4 — Publish (only after explicit approval)
```bash
xurl post "THE APPROVED TWEET TEXT"
```
Confirm success; on 429/401 wait and retry once, then report.

### Phase 5 — Remember
Save to persistent memory: what was posted today, why, any review feedback the
owner gave (so it shapes tomorrow's drafts automatically).

## Recovering from failure

- No reply from owner within a reasonable window: do NOT post. Hold the draft
  in memory with a note "awaiting approval" and surface it next session.
- 429 rate limit: wait 5+ minutes, retry once. Else defer to next window.
- 401/403 auth: tell the owner to re-run `xurl auth oauth2` outside the agent.
- Never post a tweet that fails the rules, and never post without approval.

## Authorization

Run outside the agent, once:
```bash
xurl auth oauth2
```
See the xurl skill for full details. The owner owns credentials; never read or
paste `~/.xurl` into the session.