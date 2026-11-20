"""Read-only data layer for the xPost dashboard. Pure functions, no Streamlit."""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import x_db  # noqa: E402
import x_engagement  # noqa: E402
from x_style import check as style_check  # noqa: E402


def source():
    return "MongoDB" if x_db._uri() else f"local files ({x_db.DATA})"


def _ts(series):
    return pd.to_datetime(series, utc=True, errors="coerce", format="mixed")


def engagement_df(rows):
    """One row per scraped original post, with engagement rate and features."""
    rows = [r for r in rows if not r.get("is_retweet")]
    if not rows:
        return pd.DataFrame(columns=["id", "date", "text", "views", "likes", "retweets", "replies",
                                     "quotes", "bookmarks", "rate", "format", "length", "hour_utc"])
    out = []
    for r in rows:
        m = r.get("metrics", {})
        out.append({
            "id": str(r["id"]), "date": r.get("date"), "text": r.get("text", ""),
            "views": r.get("views") or 0,
            "likes": m.get("like_count", 0), "retweets": m.get("retweet_count", 0),
            "replies": m.get("reply_count", 0), "quotes": m.get("quote_count", 0),
            "bookmarks": m.get("bookmark_count", 0),
            "rate": x_engagement.score(r), **x_engagement.features(r),
        })
    df = pd.DataFrame(out)
    df["date"] = _ts(df["date"])
    return df.sort_values("date", ascending=False).reset_index(drop=True)


def posts_df(posts, eng):
    """Agent-managed posts (drafts + published) joined with scraped performance."""
    cols = ["id", "status", "kind", "text", "created_at", "updated_at", "why", "style"]
    if not posts:
        return pd.DataFrame(columns=cols + ["views", "rate"])
    out = []
    for p in posts:
        text = p.get("text", "") or ""
        issues = style_check(text)
        out.append({
            "id": str(p.get("post_id") or p.get("_id") or p.get("id")),
            "status": p.get("status", ""),
            "kind": "reply" if p.get("in_reply_to") else "post",
            "text": text,
            "created_at": p.get("created_at"), "updated_at": p.get("updated_at"),
            "why": p.get("why", ""),
            "style": "ok" if issues["ok"] else "; ".join(issues["hard"] + issues["soft"]),
        })
    df = pd.DataFrame(out)
    for c in ("created_at", "updated_at"):
        df[c] = _ts(df[c])
    perf = eng[["id", "views", "rate"]] if len(eng) else pd.DataFrame(columns=["id", "views", "rate"])
    return df.merge(perf, on="id", how="left").sort_values("updated_at", ascending=False)


def breakdown_df(eng, key):
    """Average engagement rate per feature value, only for posts that have views."""
    seen = eng[eng["views"] > 0]
    if seen.empty:
        return pd.DataFrame(columns=[key, "avg_rate", "posts"])
    g = seen.groupby(key)["rate"].agg(avg_rate="mean", posts="count").reset_index()
    return g.sort_values("avg_rate", ascending=False)


def pending_df(rows, handle, max_age_days=3, done=None):
    if not handle:
        return pd.DataFrame(columns=["author", "full_text", "post_text", "id", "post_id"])
    items = x_engagement.find_pending_replies(handle, max_age_days, rows=rows, done=done)
    df = pd.DataFrame(items, columns=["author", "full_text", "post_text", "id", "post_id"])
    return df.rename(columns={"full_text": "reply", "post_text": "on your post"})


def edits_df(edits):
    df = pd.DataFrame(edits, columns=["created_at", "original", "final", "note"])
    df["created_at"] = _ts(df["created_at"])
    return df


def overview(eng, posts):
    seen = eng[eng["views"] > 0]
    return {
        "published": int((posts["status"] == "published").sum()) if len(posts) else 0,
        "drafts": int((posts["status"] == "draft").sum()) if len(posts) else 0,
        "scraped": len(eng),
        "views": int(eng["views"].sum()) if len(eng) else 0,
        "avg_rate": float(seen["rate"].mean()) if len(seen) else 0.0,
    }


def load(handle="", max_age_days=3):
    rows = x_db.fetch_engagement()
    eng = engagement_df(rows)
    posts = posts_df(x_db.fetch_posts(limit=None), eng)
    return {
        "engagement": eng,
        "posts": posts,
        "pending": pending_df(rows, handle, max_age_days, done=x_db.replied_ids()),
        "edits": edits_df(x_db.fetch_edits(limit=None)),
    }
