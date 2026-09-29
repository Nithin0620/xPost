#!/usr/bin/env python3
"""Durable store for xPost: drafts, published posts, engagement snapshots.

Reads MONGODB_URI from .env (MongoDB Atlas). If unset, falls back to local
JSONL so the tool chain keeps working before Atlas is configured.

Usage:
  x_db.py save-post --status draft --payload '<json>'       # agent saves a draft
  x_db.py save-post --status published --payload '<json>'   # agent saves a publish
"""
import argparse
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
POSTS_FILE = DATA / "posts.jsonl"


def _load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _uri():
    _load_env()
    return os.environ.get("MONGODB_URI", "").strip()


def _collection(name):
    import pymongo
    u = _uri()
    client = pymongo.MongoClient(u, serverSelectionTimeoutMS=5000)
    dbname = u.split("/")[-1].split("?")[0]
    return client[dbname if dbname else "xpost"][name]


def _append_local(path, doc):
    DATA.mkdir(exist_ok=True)
    rows = []
    if path.exists():
        rows = [json.loads(l) for l in path.read_text().splitlines()]
    # dedupe by _id so repeated saves (draft -> published) update, not duplicate
    rows = [r for r in rows if r.get("_id") != doc.get("_id")] + [doc]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    print(f"no MONGODB_URI set; saved locally to {path}")


def save_engagement(rows):
    """Upsert scraped post rows into `engagement`. No-op locally (jsonl is the store)."""
    if not rows or not _uri():
        return
    col = _collection("engagement")
    for r in rows:
        col.update_one({"_id": r["id"]}, {"$set": {**r, "updated_at": _now()}}, upsert=True)
    print(f"upserted {len(rows)} engagement rows -> mongo")


def save_post(status, payload):
    doc = payload if isinstance(payload, dict) else json.loads(payload)
    _id = str(doc.get("id") or f"t{int(time.time())}")
    doc.update({"_id": _id, "status": status, "updated_at": _now()})
    doc.setdefault("created_at", doc["updated_at"])
    if _uri():
        _collection("posts").update_one({"_id": _id}, {"$set": doc}, upsert=True)
        print(f"post {_id} [{status}] saved -> mongo")
    else:
        _append_local(POSTS_FILE, doc)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--save-post", action="store_true")
    ap.add_argument("--status", choices=["draft", "published"])
    ap.add_argument("--payload", default="")
    a = ap.parse_args()
    if a.save_post:
        if not a.status or not a.payload:
            ap.error("--save-post requires --status and --payload")
        save_post(a.status, a.payload)
    else:
        ap.print_help()