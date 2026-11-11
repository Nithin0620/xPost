import json

import x_db


def test_save_post_upserts_by_id(local_db):
    x_db.save_post("draft", {"id": "a", "text": "draft"})
    x_db.save_post("published", {"id": "a", "text": "final"})
    rows = [json.loads(l) for l in (local_db / "posts.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["status"] == "published" and rows[0]["text"] == "final"


def test_list_posts_filters_newest_first(local_db, capsys):
    for i, st in enumerate(["draft", "published", "published"]):
        x_db.save_post(st, {"id": str(i)})
    out = x_db.list_posts(status="published", limit=1)
    assert [p["_id"] for p in out] == ["2"]


def test_edits_skip_unchanged(local_db):
    x_db.save_edit("same", "same")
    assert not (local_db / "edits.jsonl").exists()
    x_db.save_edit("The future is AI", "ai on my wrist is mid", "casual")
    assert x_db.list_edits()[0]["final"] == "ai on my wrist is mid"


def test_replied_ids(local_db):
    assert x_db.replied_ids() == set()
    x_db.save_post("published", {"id": "n1", "text": "yep", "in_reply_to": "r1"})
    x_db.save_post("published", {"id": "n2", "text": "post"})
    assert x_db.replied_ids() == {"r1"}
