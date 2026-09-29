#!/usr/bin/env python3
"""Own-profile X engagement scraper (no official API).

Uses twscrape's X GraphQL implementation with your own account session on disk.
Reads your profile only: last N posts, their public metrics, and top replies.

Auth (pick one — browser-session cookies work even when Cloudflare blocks logins):
  x_engagement.py --cookies <auth/x_cookies.json> --cookies-username <user>
                     # inject cookies exported from a logged-in X browser session
  x_engagement.py --login "<user>" "<password>" [--email ... --email-pass ...]
                     # fallback password login (often blocked by Cloudflare)

Then:
  x_engagement.py --fetch --handle <handle> [--limit 20]    # scrape + summarize
  x_engagement.py --selfcheck
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

import twscrape

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ENGAGEMENT_FILE = DATA / "engagement.jsonl"


def _load_cookies(path):
    data = Path(path).read_text()
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        pass
    out = {}
    for line in data.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" in line and len(parts := line.split("\t")) >= 7:  # Netscape cookies.txt
            out[parts[5]] = parts[6]
        elif "=" in line and ";" in line:                          # Cookie header
            out.update(x.strip().split("=", 1) for x in line.split(";") if "=" in x)
    return out


def login_with_cookies(path, username):
    import asyncio
    api = twscrape.API()
    async def run():
        await api.pool.add_account_cookies(username, json.dumps(_load_cookies(path)))
    try:
        asyncio.run(run())
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    active = _is_active(username)
    print(f"cookies injected for {username}; active={active}")
    if not active:
        print(f"ERROR: session inactive. Cookies need auth_token + ct0 and a valid login.")
        sys.exit(1)


def _is_active(username):
    db = ROOT / "accounts.db"
    try:
        conn = sqlite3.connect(db)
        row = conn.execute("select active from accounts where username=?", (username,)).fetchone()
        conn.close()
        return bool(row and row[0])
    except sqlite3.Error:
        return False


def login(username, password, email="", email_password=""):
    import asyncio
    api = twscrape.API()
    async def run():
        await api.pool.add_account(username, password, email, email_password)
        await api.pool.login_all()
    asyncio.run(run())
    active = _is_active(username)
    print(f"login attempted for {username}; active={active}")
    if not active:
        print(f"ERROR: session inactive (likely Cloudflare block). Use --cookies instead.")
        sys.exit(1)


def fetch(handle, limit):
    import asyncio
    async def run():
        api = twscrape.API()
        user = await api.user_by_login(handle)
        tweets = await twscrape.gather(api.user_tweets(user.id, limit=limit))
        rows = []
        for t in tweets:
            replies = await twscrape.gather(api.tweet_replies(t.id, limit=5))
            inner = t.retweetedTweet or t  # RT wrapper carries zeroed metrics; use original
            rows.append({
                "id": str(t.id),
                "date": str(t.date),
                "text": t.rawContent,
                "metrics": {
                    "like_count": inner.likeCount,
                    "retweet_count": inner.retweetCount,
                    "reply_count": inner.replyCount,
                    "quote_count": inner.quoteCount,
                },
                "views": t.viewCount,  # ponytail: viewCount lives only on outer RT tweet
                "sample_replies": [
                    {
                        "full_text": r.rawContent,
                        "public_metrics": {"like_count": r.likeCount, "reply_count": r.replyCount},
                    }
                    for r in replies[:5]
                ],
            })
        existing = set()
        if ENGAGEMENT_FILE.exists():
            existing = {json.loads(l)["id"] for l in ENGAGEMENT_FILE.read_text().splitlines()}
        new_rows = [r for r in rows if r["id"] not in existing]  # dedup across pagination retries
        DATA.mkdir(exist_ok=True)
        with ENGAGEMENT_FILE.open("a") as f:
            for r in new_rows:
                f.write(json.dumps(r) + "\n")
        print(f"appended {len(new_rows)} new rows ({len(rows) - len(new_rows)} dupes skipped)")
        from x_db import save_engagement
        save_engagement(new_rows)
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
    ap.add_argument("--cookies", metavar="COOKIES_JSON", default="",
                    help="path to browser-exported X cookies to inject")
    ap.add_argument("--cookies-username", default="",
                    help="account username the cookies belong to")
    ap.add_argument("--login", nargs=2, metavar=("USERNAME", "PASSWORD"))
    ap.add_argument("--email", default="")
    ap.add_argument("--email-pass", default="")
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--handle", default="")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        selfcheck()
    elif a.cookies:
        login_with_cookies(a.cookies, a.cookies_username)
    elif a.login:
        login(a.login[0], a.login[1], a.email, a.email_pass)
    elif a.fetch:
        fetch(a.handle, a.limit)
    else:
        ap.print_help(); sys.exit(0)