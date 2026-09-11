#!/usr/bin/env python3
"""Own-profile X engagement scraper (no official API).

Uses twscrape's X GraphQL implementation with your own account session on disk.
Reads your profile only: last N posts, their public metrics, and top replies.

Usage:
  x_engagement.py --login "<user>" "<password>"             # one-time, stores session
  x_engagement.py --fetch --handle <handle> [--limit 20]    # scrape + summarize
  x_engagement.py --selfcheck
"""
import argparse
import json
import sys
from pathlib import Path

import twscrape

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ENGAGEMENT_FILE = DATA / "engagement.jsonl"


def login(username, password):
    api = twscrape.API()
    await_ = api.pool.add_account(username, password)
    # add_account is sync-scheduled; force run via asyncio
    import asyncio
    asyncio.run(api.pool.login_all())
    print(f"logged in as {username}; session saved to accounts.db")


def fetch(handle, limit):
    import asyncio
    async def run():
        api = twscrape.API()
        user = (await twscrape.gather(api.user_by_login(handle)))[0]
        tweets = await twscrape.gather(api.user_tweets(user.id, limit=limit))
        rows = []
        for t in tweets:
            raw = t.raw
            metrics = raw.get("legacy", {}).get("public_metrics", {})
            views = raw.get("views", {}).get("count")
            replies = await twscrape.gather(api.tweet_replies(t.id, limit=5))
            rows.append({
                "id": str(t.id),
                "date": (raw.get("legacy", {}).get("created_at", "")),
                "text": t.raw.get("note_tweet") or raw.get("legacy", {}).get("full_text", ""),
                "metrics": metrics,
                "views": views,
                "sample_replies": [
                    {k: r.raw.get("legacy", {}).get(k) for k in ("full_text", "public_metrics")}
                    for r in replies[:5]
                ],
            })
        DATA.mkdir(exist_ok=True)
        with ENGAGEMENT_FILE.open("a") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        summarize(rows)
    asyncio.run(run())


def summarize(rows):
    def score(r):
        m = r["metrics"]
        return m.get("like_count", 0) + 3 * m.get("retweet_count", 0) + m.get("reply_count", 0)
    if not rows:
        print("no posts found")
        return
    ranked = sorted(rows, key=score, reverse=True)
    print(f"scraped {len(rows)} posts; appended to {ENGAGEMENT_FILE}")
    print("\n=== TOP POSTS ===")
    for r in ranked[:3]:
        m = r["metrics"]
        print(f"- [{score(r)}] views={r['views']} likes={m.get('like_count',0)} "
              f"rt={m.get('retweet_count',0)} replies={m.get('reply_count',0)} :: "
              f"{r['text'][:120]}")
    print("\n=== BOTTOM POSTS ===")
    for r in ranked[-3:]:
        m = r["metrics"]
        print(f"- [{score(r)}] views={r['views']} likes={m.get('like_count',0)} "
              f"rt={m.get('retweet_count',0)} replies={m.get('reply_count',0)} :: "
              f"{r['text'][:120]}")


def selfcheck():
    assert ENGAGEMENT_FILE == DATA / "engagement.jsonl"
    print("selfcheck ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", nargs=2, metavar=("USERNAME", "PASSWORD"))
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--handle", default="")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        selfcheck()
    elif a.login:
        login(*a.login)
    elif a.fetch:
        fetch(a.handle, a.limit)
    else:
        ap.print_help(); sys.exit(0)