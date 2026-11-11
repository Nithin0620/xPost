import random

import pytest

from x_schedule import parse_windows, plan


def _mins(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def test_times_inside_windows_and_spaced():
    for seed in range(50):
        res = plan(3, "08:00-12:00,18:00-23:00", min_gap=90, skip_chance=0, rng=random.Random(seed))
        mins = [_mins(t) for t in res["times"]]
        assert mins == sorted(mins) and len(mins) == 3
        assert all(480 <= m < 720 or 1080 <= m < 1380 for m in mins)
        assert all(b - a >= 90 for a, b in zip(mins, mins[1:]))


def test_skip_and_narrow_window():
    assert plan(2, skip_chance=1.0)["skip"]
    assert plan(0)["skip"]
    res = plan(4, "09:00-10:00", min_gap=90, skip_chance=0, rng=random.Random(1))
    assert len(res["times"]) == 1


def test_bad_window():
    with pytest.raises(ValueError):
        parse_windows("10:00-09:00")
