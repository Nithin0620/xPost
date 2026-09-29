#!/usr/bin/env python3
"""Own-profile X engagement scraper & direct session publisher (no official API).

Uses twscrape's X GraphQL implementation with your own account session on disk.
Reads your profile only: last N posts, their public metrics, and top replies.
Supports publishing tweets directly via browser session cookies (free, no API keys needed).

Auth (pick one — browser-session cookies work even when Cloudflare blocks logins):
  x_engagement.py --cookies <auth/x_cookies.json> --cookies-username <user>
                     # inject cookies exported from a logged-in X browser session
  x_engagement.py --login "<user>" "<password>" [--email ... --email-pass ...]
                     # fallback password login (often blocked by Cloudflare)

Usage:
  x_engagement.py --fetch --handle <handle> [--limit 20]    # scrape + summarize
  x_engagement.py --post "Your tweet text here"             # publish tweet via cookies
  x_engagement.py --selfcheck
"""
import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

import httpx
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
                "views": t.viewCount,
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


def _resolve_create_tweet_query_id(cookie_dict):
    known = "WNkbkQ_JLIofjdukTXahVA"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "cookie": "; ".join(f"{k}={v}" for k, v in cookie_dict.items()),
    }
    try:
        with httpx.Client(follow_redirects=True, timeout=8.0, headers=headers) as client:
            r = client.get("https://x.com/home")
            js_match = re.search(r'https://abs\.twimg\.com/responsive-web/client-web/main\.[a-zA-Z0-9]+\.js', r.text)
            if js_match:
                main_js = client.get(js_match.group(0)).text
                m = re.search(r'queryId:\"([^\"]+)\",operationName:\"CreateTweet\"', main_js)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return known


def post_tweet(text, cookies_path=None):
    """Publish a tweet directly using browser session cookies via X GraphQL API."""
    if not cookies_path:
        cookies_path = ROOT / "auth" / "x_cookies.json"
    raw_cookies = _load_cookies(cookies_path)
    if isinstance(raw_cookies, list):
        cookie_dict = {c["name"]: c["value"] for c in raw_cookies if "name" in c and "value" in c}
    else:
        cookie_dict = raw_cookies

    auth_token = cookie_dict.get("auth_token")
    ct0 = cookie_dict.get("ct0")
    if not auth_token or not ct0:
        print("ERROR: auth_token and ct0 cookies are required to post.", file=sys.stderr)
        sys.exit(1)

    headers = {
        "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
        "x-csrf-token": ct0,
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-active-user": "yes",
        "content-type": "application/json",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "cookie": "; ".join(f"{k}={v}" for k, v in cookie_dict.items()),
    }

    qid = _resolve_create_tweet_query_id(cookie_dict)
    query_ids = [qid, "WNkbkQ_JLIofjdukTXahVA", "5V_dkq1kcR8yTuhAuRwjwA"]

    features = {
        "communities_web_enable_tweet_community_results_fetch": True,
        "c9s_tweet_anatomy_moderator_badge_enabled": True,
        "tweetypie_unmention_optimization_enabled": True,
        "responsive_web_edit_tweet_api_enabled": True,
        "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
        "view_counts_everywhere_api_enabled": True,
        "longform_notetweets_consumption_enabled": True,
        "responsive_web_twitter_article_tweet_consumption_enabled": True,
        "tweet_awards_web_tipping_enabled": False,
        "creator_subscriptions_quote_tweet_preview_enabled": False,
        "freedom_of_speech_not_reach_fetch_enabled": True,
        "standardized_nudges_misinfo": True,
        "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
        "rweb_video_timestamps_enabled": True,
        "longform_notetweets_rich_text_read_enabled": True,
        "longform_notetweets_inline_media_enabled": True,
        "rweb_tipjar_consumption_enabled": True,
        "responsive_web_graphql_exclude_directive_enabled": True,
        "verified_phone_label_enabled": False,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "responsive_web_graphql_timeline_navigation_enabled": True,
        "responsive_web_enhance_cards_enabled": False,
    }

    seen = set()
    for q in query_ids:
        if q in seen:
            continue
        seen.add(q)
        url = f"https://x.com/i/api/graphql/{q}/CreateTweet"
        payload = {
            "variables": {
                "tweet_text": text,
                "dark_request": False,
                "media": {"media_entities": [], "possibly_sensitive": False},
                "semantic_annotation_ids": [],
            },
            "features": features,
            "queryId": q,
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    if "errors" in data and not data.get("data"):
                        print(f"GraphQL note ({q}): {data['errors']}", file=sys.stderr)
                        continue
                    tweet_result = (data.get("data", {})
                                    .get("create_tweet", {})
                                    .get("tweet_results", {})
                                    .get("result", {}))
                    tweet_id = tweet_result.get("rest_id", "")
                    print(f"SUCCESS: Tweet published! ID: {tweet_id}")
                    from x_db import save_post
                    save_post("published", {"id": tweet_id or "tw_cookie", "text": text, "post_id": tweet_id})
                    return {"id": tweet_id, "text": text, "status": "published"}
                else:
                    print(f"HTTP {res.status_code} ({q}): {res.text[:160]}", file=sys.stderr)
        except Exception as e:
            print(f"Request failed ({q}): {e}", file=sys.stderr)

    print("ERROR: Failed to publish tweet with cookies.", file=sys.stderr)
    sys.exit(1)


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
    ap.add_argument("--post", metavar="TEXT", help="post a tweet directly using browser session cookies")
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
    elif a.post:
        post_tweet(a.post)
    else:
        ap.print_help(); sys.exit(0)