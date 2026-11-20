import pytest

from x_style import check

AI_DRAFTS = [
    "AI isn't just in the cloud anymore. The real edge is on your wrist.",
    "This is a game-changer — it will revolutionize the landscape.",
    "It's not just a tool, it's a paradigm. Let's delve into it.",
]
HUMAN_DRAFTS = [
    "spent 3 hours debugging a cron job that was running in UTC. every time.",
    "shipped the scraper today, finally",
    "unpopular opinion: most side projects die because of auth, not ideas",
]


@pytest.mark.parametrize("text", AI_DRAFTS)
def test_flags_ai_sounding(text):
    assert not check(text)["ok"]


@pytest.mark.parametrize("text", HUMAN_DRAFTS)
def test_passes_human_sounding(text):
    assert check(text)["ok"], check(text)


def test_hard_rules():
    assert "too long" in check("x" * 261)["hard"][0]
    assert check("read this https://example.com")["hard"]
    assert check("#a #b #c ok")["hard"]
    assert not check("#a #b ok")["hard"]
