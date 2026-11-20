import json
from datetime import datetime, timedelta, timezone

import x_db
import x_engagement as e


def row(id, text, views, likes=0, replies=0, hours_ago=1, sample=(), **kw):
    when = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return {"id": id, "date": when.isoformat(), "text": text, "views": views,
            "metrics": {"like_count": likes, "reply_count": replies},
            "sample_replies": list(sample), **kw}


def test_score_is_rate_per_view():
    assert e.score(row("1", "a", 100, likes=10, replies=2)) == 0.16
    assert e.score(row("1", "a", None, likes=10)) == 0.0


def test_breakdown_groups_by_format():
    rows = [row("1", "why?", 100, likes=10), row("2", "a statement", 100, likes=1)]
    fmt = dict((v, avg) for v, avg, _ in e.breakdown(rows)["format"])
    assert fmt["question"] > fmt["statement"]


def test_upsert_refreshes_metrics(local_db):
    e._upsert_local([row("1", "a", 10, likes=0)])
    e._upsert_local([row("1", "a", 500, likes=40), row("2", "b", 5)])
    rows = {r["id"]: r for r in e.load_rows()}
    assert len(rows) == 2 and rows["1"]["metrics"]["like_count"] == 40


def test_summarize_skips_retweets_and_viewless(local_db, capsys):
    e.summarize([row("1", "rt", 10, likes=99, is_retweet=True), row("2", "x", 0)])
    assert "no original posts" in capsys.readouterr().out


def test_pending_replies_filters(local_db):
    sample = [{"id": "r1", "author": "alice"}, {"id": "r2", "author": "Me"},
              {"id": "r3", "author": "bob"}]
    e._upsert_local([row("1", "post", 100, sample=sample),
                     row("2", "old", 100, hours_ago=24 * 10, sample=[{"id": "r9", "author": "x"}])])
    x_db.save_post("published", {"id": "n", "text": "answered", "in_reply_to": "r3"})
    out = e.pending_replies("me")
    assert [r["id"] for r in out] == ["r1"]
