#!/usr/bin/env python3
import json
import random
import subprocess
import sys
import urllib.request
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))
from x_style import check as style_check  # noqa: E402

VOICE_FILE = ROOT / ".hermes" / "skills" / "x-post" / "VOICE.md"
EXAMPLES_FILE = ROOT / ".hermes" / "skills" / "x-post" / "examples.md"
MEMORY_FILE = ROOT / "memory.json"
MAX_LEN = 260
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_MODEL = "gemini-3.1-flash-lite"


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
    return voice_context() + base + f" Max {MAX_LEN} chars, no links, no hashtag spam." + suffix


def voice_context():
    parts = [f.read_text() for f in (VOICE_FILE, EXAMPLES_FILE) if f.exists()]
    if not parts:
        return ""
    return "Write in this voice:\n" + "\n\n".join(parts) + "\n\nTask: "


def generate(api_key, prompt, model=DEFAULT_MODEL):
    client = OpenAI(api_key=api_key, base_url=GEMINI_BASE_URL)
    res = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
    )
    return res.choices[0].message.content.strip()


def filter_tweet(text, mem):
    text = text.strip("\"'")
    if not text or len(text) > MAX_LEN or text in mem["posted"]:
        return None
    if not style_check(text)["ok"]:
        return None
    return text


def post(text):
    res = subprocess.run(["xurl", "post", text], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"xurl post failed: {res.stderr.strip() or res.stdout.strip()}")
    from x_db import save_post
    tweet_id = ""
    try:
        tweet_id = json.loads(res.stdout).get("data", {}).get("id", "")
    except (json.JSONDecodeError, AttributeError):
        pass
    save_post("published", {"id": tweet_id or None, "text": text, "post_id": tweet_id})


def main(argv):
    env = load_env()
    mem = memory()
    mode = pick_mode()
    github = github_context(env.get("GITHUB_USERNAME", ""))
    prompt = build_prompt(mode, github, mem["topics"], mem["posted"])
    text = None
    for _ in range(3):
        text = filter_tweet(generate(env["GEMINI_API_KEY"], prompt,
                                     env.get("GEMINI_MODEL") or DEFAULT_MODEL), mem)
        if text:
            break
    if not text:
        print("no acceptable tweet generated, skipping run")
        return 0
    if "--dry-run" in argv:
        print(f"[{mode}] {text}")
        return 0
    post(text)
    mem["posted"].append(text)
    if len(mem["posted"]) > 500:
        mem["posted"] = mem["posted"][-500:]
    save(mem)
    print(f"posted ({mode}): {text}")
    return 0


def selfcheck():
    assert filter_tweet("hi", {"posted": []}) == "hi"
    assert filter_tweet("x" * (MAX_LEN + 1), {"posted": []}) is None
    assert filter_tweet("see https://x.com", {"posted": []}) is None
    assert filter_tweet("hi", {"posted": ["hi"]}) is None
    assert "Do NOT repeat" in build_prompt("free", "", [], ["old tweet"])
    assert "Do NOT repeat" not in build_prompt("free", "", [], [])
    assert filter_tweet("this isn't just a tool, it's a game-changer", {"posted": []}) is None
    print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        selfcheck()
    else:
        sys.exit(main(sys.argv))