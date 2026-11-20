import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "dashboard"))
import data  # noqa: E402
import x_db  # noqa: E402
import x_engagement  # noqa: E402


def row(id, text, views, likes=0, replies=0, hours_ago=1, sample=(), **kw):
    when = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return {"id": id, "date": when.isoformat(), "text": text, "views": views,
            "metrics": {"like_count": likes, "reply_count": replies},
            "sample_replies": list(sample), **kw}


@pytest.fixture
def seeded(local_db):
    x_engagement._upsert_local([
        row("1", "why does docker eat my disk?", 200, likes=10, replies=2,
            sample=[{"id": "r1", "author": "bob", "full_text": "prune it"}]),
        row("2", "shipped the parser today", 100, likes=1),
        row("3", "rt", 0, is_retweet=True),
    ])
    x_db.save_post("published", {"id": "2", "text": "shipped the parser today", "post_id": "2"})
    x_db.save_post("draft", {"id": "d1", "text": "It's not just code, it's a game-changer"})
    x_db.save_edit("The future is AI", "ai on my wrist is mid", "casual")
    return local_db


def test_load_joins_posts_with_engagement(seeded):
    d = data.load("me")
    eng, posts = d["engagement"], d["posts"]
    assert set(eng["id"]) == {"1", "2"}  # retweet dropped
    pub = posts[posts["status"] == "published"].iloc[0]
    assert pub["views"] == 100 and pub["rate"] == pytest.approx(0.01)
    draft = posts[posts["status"] == "draft"].iloc[0]
    assert draft["style"] != "ok"
    assert list(d["pending"]["id"]) == ["r1"]
    assert d["edits"].iloc[0]["final"] == "ai on my wrist is mid"
    o = data.overview(eng, posts)
    assert (o["published"], o["drafts"], o["views"]) == (1, 1, 300)


def test_answered_replies_are_hidden(seeded):
    x_db.save_post("published", {"id": "n1", "text": "yep", "in_reply_to": "r1"})
    assert data.load("me")["pending"].empty


def test_breakdown_ranks_formats(seeded):
    b = data.breakdown_df(data.load()["engagement"], "format")
    assert b.iloc[0]["format"] == "question"


def test_empty_store(local_db):
    d = data.load("me")
    assert all(d[k].empty for k in ("engagement", "posts", "pending", "edits"))


@pytest.mark.parametrize("fixture", ["local_db", "seeded"])
def test_app_renders(fixture, request, monkeypatch):
    request.getfixturevalue(fixture)
    monkeypatch.setenv("X_HANDLE", "me")
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(Path(data.ROOT) / "dashboard" / "app.py"), default_timeout=30).run()
    assert not at.exception
    assert len(at.tabs) == 6
