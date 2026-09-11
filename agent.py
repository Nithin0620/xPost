#!/usr/bin/env python3
import json
import random
import sys
import urllib.request
from pathlib import Path

import tweepy
from openai import OpenAI

ROOT = Path(__file__).parent
MEMORY_FILE = ROOT / "memory.json"
MAX_LEN = 280


def load_env():
    env = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def memory():
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text())
    return {"topics": [], "posted": []}


def save(mem):
    MEMORY_FILE.write_text(json.dumps(mem, indent=2))


def github_context(user):
    if not user:
        return ""
    url = f"https://api.github.com/users/{user}/repos?sort=updated&per_page=5"
    req = urllib.request.Request(url, headers={"User-Agent": "xpost"})
    with urllib.request.urlopen(req) as r:
        repos = json.load(r)
    return "; ".join(re["name"] + (f": {re['description'][:80]}" if re.get("description") else "")
                     for re in repos)


def pick_mode():
    return random.choice(["dev", "topic", "github", "free"])


def build_prompt(mode, github, topics, past):
    base = {
        "dev": "Write one short, practical programming tip a developer would retweet.",
        "topic": f"Write an engaging tweet about one of these topics: {', '.join(topics)}.",
        "github": f"Write a tweet introducing or describing my recent GitHub work: {github}.",
        "free": "Write a short, original, thought-provoking tweet.",
    }[mode]
    anti = "; ".join(past[-10:])
    suffix = f" Do NOT repeat the ideas of past tweets: {anti}." if anti else ""
    return base + " Max 280 chars, no hashtag spam." + suffix


def generate(api_key, prompt):
    client = OpenAI(api_key=api_key)
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
    )
    return res.choices[0].message.content.strip()


def filter_tweet(text, mem):
    text = text.strip("\"'")
    if not text or len(text) > MAX_LEN or text in mem["posted"]:
        return None
    return text


def post(env, text):
    client = tweepy.Client(
        consumer_key=env["X_API_KEY"],
        consumer_secret=env["X_API_SECRET"],
        access_token=env["X_ACCESS_TOKEN"],
        access_token_secret=env["X_ACCESS_TOKEN_SECRET"],
    )
    client.create_tweet(text=text)


def main(argv):
    env = load_env()
    mem = memory()
    mode = pick_mode()
    github = github_context(env.get("GITHUB_USERNAME", ""))
    prompt = build_prompt(mode, github, mem["topics"], mem["posted"])
    text = None
    for _ in range(3):
        text = filter_tweet(generate(env["OPENAI_API_KEY"], prompt), mem)
        if text:
            break
    if not text:
        print("no acceptable tweet generated, skipping run")
        return 0
    mem["posted"].append(text)
    if len(mem["posted"]) > 500:
        mem["posted"] = mem["posted"][-500:]
    save(mem)
    if "--dry-run" in argv:
        print(f"[{mode}] {text}")
        return 0
    post(env, text)
    print(f"posted ({mode}): {text}")
    return 0


def selfcheck():
    assert filter_tweet("hi", {"posted": []}) == "hi"
    assert filter_tweet("x" * 281, {"posted": []}) is None
    assert filter_tweet("hi", {"posted": ["hi"]}) is None
    assert "Do NOT repeat" in build_prompt("free", "", [], ["old tweet"])
    assert "Do NOT repeat" not in build_prompt("free", "", [], [])
    print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        selfcheck()
    else:
        sys.exit(main(sys.argv))