#!/usr/bin/env python3
"""Flag AI-sounding patterns in a tweet draft before it goes to review.

Usage:
  x_style.py check "draft text"        # prints issues; exit 1 if the draft should be rewritten
  x_style.py check --json "draft text"
"""
import argparse
import json
import re
import sys

MAX_LEN = 260

BUZZWORDS = [
    "delve", "game-changer", "game changer", "unlock", "unleash", "leverage",
    "landscape", "realm", "tapestry", "elevate", "seamless", "seamlessly",
    "robust", "revolutionize", "revolutionizing", "cutting-edge", "paradigm",
    "synergy", "harness", "embark", "testament", "supercharge", "empower",
    "transformative", "ever-evolving", "fast-paced", "in today's world",
    "in today's digital", "the real edge", "next wave", "here's the thing",
    "let that sink in", "buckle up", "the future is", "it's worth noting",
    "at the end of the day", "dive into", "deep dive",
]

HARD = [
    (r"https?://|www\.", "contains a link (expensive on X, and not allowed)"),
    (r"(#\w+.*){3,}", "more than 2 hashtags"),
]

SOFT = [
    (r"[\u2014\u2013]", "em/en dash: classic LLM punctuation, use a period or comma"),
    (r"\b(it'?s|this is|that'?s|isn'?t|aren'?t|wasn'?t)\s+(not\s+)?(just|only|merely)\b",
     "'it's not just X' construction"),
    (r"\bnot\s+(just|only)\b[^.?!]*\bbut\b", "'not just X but Y' construction"),
    (r"\bisn'?t about\b[^.?!]*\bit'?s about\b", "'isn't about X, it's about Y' construction"),
    (r"^(ever wondered|imagine|let'?s talk about|here'?s why|did you know)\b", "stock opener"),
    (r"(^|[.?!]\s+)(the (real |key )?(lesson|takeaway|future|secret)|remember:|bottom line)[^.?!]*[.?!]?\s*$",
     "ends on a moral/lesson"),
    (r"\b\w+, \w+,? and \w+\b", "list of three (rule-of-three cadence)"),
    (r"!.*!", "multiple exclamation marks"),
]

EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def check(text):
    issues = {"hard": [], "soft": []}
    t = text.strip()
    low = t.lower()
    if len(t) > MAX_LEN:
        issues["hard"].append(f"too long ({len(t)} > {MAX_LEN})")
    for pat, msg in HARD:
        if re.search(pat, t, re.I | re.S):
            issues["hard"].append(msg)
    for pat, msg in SOFT:
        if re.search(pat, low, re.M):
            issues["soft"].append(msg)
    hits = [w for w in BUZZWORDS if re.search(r"\b" + re.escape(w) + r"\b", low)]
    if hits:
        issues["soft"].append("AI buzzwords: " + ", ".join(hits))
    if len(EMOJI.findall(t)) > 1:
        issues["soft"].append("more than one emoji")
    issues["ok"] = not issues["hard"] and len(issues["soft"]) < 2
    return issues


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("text")
    c.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    res = check(a.text)
    if a.json:
        print(json.dumps(res))
    else:
        print("OK" if res["ok"] else "REWRITE")
        for level in ("hard", "soft"):
            for msg in res[level]:
                print(f"- [{level}] {msg}")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
