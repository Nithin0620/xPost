#!/usr/bin/env python3
"""Own-profile X engagement scraper (read-only, no official API).

Uses twscrape's X GraphQL implementation with your own account session on disk.
Reads your profile only: last N posts, their public metrics, and top replies.
Publishing is NOT done here: posting goes through `xurl post` (official API) only.

Auth (pick one — browser-session cookies work even when Cloudflare blocks logins):
  x_engagement.py --cookies <auth/x_cookies.json> --cookies-username <user>
                     # inject cookies exported from a logged-in X browser session
  x_engagement.py --login "<user>" "<password>" [--email ... --email-pass ...]
                     # fallback password login (often blocked by Cloudflare)

Usage:
  x_engagement.py --fetch --handle <handle> [--limit 20]    # scrape + summarize
  x_engagement.py --analyze                                 # re-summarize stored data, no scraping
  x_engagement.py --pending-replies --handle <handle>       # unanswered replies on recent posts
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
            replies = await twscrape.gather(api.tweet_replies(t.id, limit=10))
            inner = t.retweetedTweet or t  # RT wrapper carries zeroed metrics; use original
            rows.append({
                "id": str(t.id),
                "date": t.date.isoformat(),
                "text": t.rawContent,
                "is_retweet": t.retweetedTweet is not None,
                "has_media": bool(getattr(inner, "media", None) and
                                  (inner.media.photos or inner.media.videos or inner.media.animated)),
                "metrics": {
                    "like_count": inner.likeCount,
                    "retweet_count": inner.retweetCount,
                    "reply_count": inner.replyCount,
                    "quote_count": inner.quoteCount,
                    "bookmark_count": getattr(inner, "bookmarkedCount", 0) or 0,
                },
                "views": t.viewCount,
                "sample_replies": [
                    {
                        "id": str(r.id),
                        "author": r.user.username,
                        "full_text": r.rawContent,
                        "public_metrics": {"like_count": r.likeCount, "reply_count": r.replyCount},
                    }
                    for r in replies
                    if r.user.username.lower() != handle.lower()
                ],
            })
        _upsert_local(rows)
        print(f"stored {len(rows)} posts (metrics refreshed for already-seen posts)")
        from x_db import save_engagement
        save_engagement(rows)
        summarize(rows)
    asyncio.run(run())


def load_rows():
    if not ENGAGEMENT_FILE.exists():
        return []
    return [json.loads(l) for l in ENGAGEMENT_FILE.read_text().splitlines() if l.strip()]


def _upsert_local(rows):
    """Replace rows by id so later fetches refresh metrics instead of freezing day-0 numbers."""
    merged = {r["id"]: r for r in load_rows()}
    merged.update({r["id"]: r for r in rows})
    DATA.mkdir(exist_ok=True)
    ENGAGEMENT_FILE.write_text("".join(json.dumps(r) + "\n" for r in merged.values()))


def score(r):
    """Weighted interactions per view. Replies/quotes signal conversation, so weigh them most."""
    m = r["metrics"]
    interactions = (m.get("like_count", 0) + 2 * m.get("retweet_count", 0)
                    + 3 * m.get("reply_count", 0) + 3 * m.get("quote_count", 0)
                    + m.get("bookmark_count", 0))
    views = r.get("views") or 0
    return interactions / views if views else 0.0


def features(r):
    text = r["text"]
    n = len(text)
    try:
        from datetime import datetime
        hour = datetime.fromisoformat(str(r["date"]).replace(" ", "T")).hour
    except ValueError:
        hour = None
    if r.get("has_media"):
        fmt = "media"
    elif text.rstrip().endswith("?"):
        fmt = "question"
    elif any(ch.isdigit() for ch in text):
        fmt = "has-number"
    else:
        fmt = "statement"
    return {
        "format": fmt,
        "length": "short (<100)" if n < 100 else "medium (100-200)" if n <= 200 else "long (>200)",
        "hour_utc": f"{hour // 3 * 3:02d}-{hour // 3 * 3 + 3:02d}h" if hour is not None else "unknown",
    }


def breakdown(rows):
    """Average engagement rate per feature value: {feature: [(value, avg_rate, n), ...]}."""
    out = {}
    for key in ("format", "length", "hour_utc"):
        buckets = {}
        for r in rows:
            buckets.setdefault(features(r)[key], []).append(score(r))
        out[key] = sorted(((v, sum(s) / len(s), len(s)) for v, s in buckets.items()),
                          key=lambda x: x[1], reverse=True)
    return out


def summarize(rows):
    rows = [r for r in rows if not r.get("is_retweet") and r.get("views")]
    if not rows:
        print("no original posts with view counts found")
        return
    ranked = sorted(rows, key=score, reverse=True)

    def line(r):
        m = r["metrics"]
        return (f"- [rate {score(r):.2%}] views={r['views']} likes={m.get('like_count', 0)} "
                f"rt={m.get('retweet_count', 0)} replies={m.get('reply_count', 0)} "
                f"quotes={m.get('quote_count', 0)} :: {r['text'][:120]}")
    print(f"analyzed {len(rows)} original posts (engagement rate = weighted interactions / views)")
    print("\n=== TOP POSTS ===")
    for r in ranked[:3]:
        print(line(r))
    print("\n=== BOTTOM POSTS ===")
    for r in ranked[3:][-3:]:
        print(line(r))
    print("\n=== WHAT WORKS (avg rate by feature, n = posts) ===")
    for key, vals in breakdown(rows).items():
        print(f"{key}: " + " | ".join(f"{v} {avg:.2%} (n={n})" for v, avg, n in vals))


def find_pending_replies(handle, max_age_days=3, rows=None, done=None):
    """Replies on the owner's recent posts that the owner hasn't answered via xPost yet."""
    from datetime import datetime, timedelta, timezone
    if done is None:
        from x_db import replied_ids
        done = replied_ids()
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    out = []
    for r in load_rows() if rows is None else rows:
        try:
            when = datetime.fromisoformat(str(r["date"]).replace(" ", "T"))
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if r.get("is_retweet") or when < cutoff:
            continue
        for rep in r.get("sample_replies", []):
            if rep.get("id") and rep["id"] not in done and \
                    rep.get("author", "").lower() != handle.lower():
                out.append({"post_id": r["id"], "post_text": r["text"], **rep})
    return out


def pending_replies(handle, max_age_days=3):
    out = find_pending_replies(handle, max_age_days)
    print(json.dumps(out, indent=2))
    return out


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
    ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--pending-replies", action="store_true")
    ap.add_argument("--max-age-days", type=int, default=3)
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
    elif a.analyze:
        summarize(load_rows())
    elif a.pending_replies:
        pending_replies(a.handle, a.max_age_days)
    else:
        ap.print_help(); sys.exit(0)