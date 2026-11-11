#!/usr/bin/env python3
"""Pick human-looking posting times: random minutes inside the owner's active
windows, minimum spacing between posts, and occasional skipped days.

Usage:
  x_schedule.py plan --posts 2 [--windows "08:30-10:30,13:00-14:00,19:00-23:00"]
                     [--min-gap 90] [--skip-chance 0.1] [--seed N]
Prints JSON: {"skip": bool, "times": ["HH:MM", ...]} in local time.
"""
import argparse
import json
import random
import sys

DEFAULT_WINDOWS = "08:30-10:30,13:00-14:00,19:00-23:00"


def _minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def parse_windows(spec):
    out = []
    for part in spec.split(","):
        start, end = part.strip().split("-")
        a, b = _minutes(start), _minutes(end)
        if b <= a:
            raise ValueError(f"window {part!r} must end after it starts")
        out.append((a, b))
    return out


def plan(posts, windows=DEFAULT_WINDOWS, min_gap=90, skip_chance=0.1, rng=None):
    rng = rng or random.Random()
    if posts <= 0 or rng.random() < skip_chance:
        return {"skip": True, "times": []}
    slots = [m for a, b in parse_windows(windows) for m in range(a, b)]
    for _ in range(200):
        picks = sorted(rng.sample(slots, min(posts, len(slots))))
        if all(b - a >= min_gap for a, b in zip(picks, picks[1:])):
            break
    else:
        picks = picks[:1]  # windows too tight for the requested spacing; post once
    return {"skip": False, "times": [f"{m // 60:02d}:{m % 60:02d}" for m in picks]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--posts", type=int, required=True)
    p.add_argument("--windows", default=DEFAULT_WINDOWS)
    p.add_argument("--min-gap", type=int, default=90, help="minutes between posts")
    p.add_argument("--skip-chance", type=float, default=0.1)
    p.add_argument("--seed", type=int)
    a = ap.parse_args(argv)
    rng = random.Random(a.seed) if a.seed is not None else None
    print(json.dumps(plan(a.posts, a.windows, a.min_gap, a.skip_chance, rng)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
