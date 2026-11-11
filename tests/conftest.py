import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))


@pytest.fixture
def local_db(tmp_path, monkeypatch):
    """Force the JSONL fallback into a temp dir so tests never touch Mongo or real data."""
    import x_db
    import x_engagement
    monkeypatch.setattr(x_db, "_uri", lambda: "")
    monkeypatch.setattr(x_db, "DATA", tmp_path)
    monkeypatch.setattr(x_db, "POSTS_FILE", tmp_path / "posts.jsonl")
    monkeypatch.setattr(x_db, "EDITS_FILE", tmp_path / "edits.jsonl")
    monkeypatch.setattr(x_engagement, "DATA", tmp_path)
    monkeypatch.setattr(x_engagement, "ENGAGEMENT_FILE", tmp_path / "engagement.jsonl")
    return tmp_path
