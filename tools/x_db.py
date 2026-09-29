#!/usr/bin/env python3
"""Durable store for xPost: drafts, published posts, engagement snapshots.

Reads MONGODB_URI from .env (MongoDB Atlas). If unset, falls back to local
JSONL so the tool chain keeps working before Atlas is configured.

Usage:
  x_db.py save-post --status draft --payload '<json>'       # agent saves a draft
  x_db.py save-post --status published --payload '<json>'   # agent saves a publish
  x_db.py list-posts [--status draft|published] [--limit 20]
"""
import argparse
import json
import os
import sys
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


def list_posts(status=None, limit=20):
    posts = []
    if _uri():
        col = _collection("posts")
        query = {"status": status} if status else {}
        cursor = col.find(query).sort("updated_at", -1).limit(limit)
        posts = list(cursor)
    else:
        if POSTS_FILE.exists():
            posts = [json.loads(l) for l in POSTS_FILE.read_text().splitlines()]
            if status:
                posts = [p for p in posts if p.get("status") == status]
            posts = posts[-limit:][::-1]
    print(json.dumps(posts, indent=2))
    return posts


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def parse_args():
    # Support both subcommand style ("save-post", "list-posts") and flag style ("--save-post", "--list-posts")
    ap = argparse.ArgumentParser(description="xPost durable database tool")
    subparsers = ap.add_subparsers(dest="subcommand")

    # save-post subcommand
    p_save = subparsers.add_parser("save-post", help="Save a draft or published post")
    p_save.add_argument("--status", choices=["draft", "published"], required=True)
    p_save.add_argument("--payload", required=True, help="JSON string payload")

    # list-posts subcommand
    p_list = subparsers.add_parser("list-posts", help="List recent posts")
    p_list.add_argument("--status", choices=["draft", "published"], default=None)
    p_list.add_argument("--limit", type=int, default=20)

    # Legacy flags on root parser
    ap.add_argument("--save-post", action="store_true")
    ap.add_argument("--list-posts", action="store_true")
    ap.add_argument("--status", choices=["draft", "published"])
    ap.add_argument("--payload", default="")
    ap.add_argument("--limit", type=int, default=20)

    return ap.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.subcommand == "save-post" or args.save_post:
        status = args.status
        payload = args.payload
        if not status or not payload:
            print("ERROR: save-post requires --status and --payload", file=sys.stderr)
            sys.exit(1)
        save_post(status, payload)
    elif args.subcommand == "list-posts" or args.list_posts:
        list_posts(status=args.status, limit=args.limit)
    else:
        print("Usage: x_db.py [save-post|list-posts] [options]")
        sys.exit(0)