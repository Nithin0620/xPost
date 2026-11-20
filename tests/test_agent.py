import json
import subprocess

import agent


def test_filter_tweet():
    assert agent.filter_tweet('"shipped it"', {"posted": []}) == "shipped it"
    assert agent.filter_tweet("x" * 261, {"posted": []}) is None
    assert agent.filter_tweet("dup", {"posted": ["dup"]}) is None
    assert agent.filter_tweet("see https://x.com", {"posted": []}) is None
    assert agent.filter_tweet("It's not just a tool, it's a game-changer", {"posted": []}) is None


def test_prompt_includes_voice_and_history():
    p = agent.build_prompt("free", "", [], ["old tweet"])
    assert "voice" in p.lower() and "old tweet" in p


def test_post_uses_xurl_and_logs(local_db, monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"data": {"id": "42"}}), stderr="")
    monkeypatch.setattr(agent.subprocess, "run", fake_run)
    agent.post("hello")
    assert calls == [["xurl", "post", "hello"]]
    row = json.loads((local_db / "posts.jsonl").read_text())
    assert row["_id"] == "42" and row["status"] == "published"


def test_dry_run_does_not_post_or_record(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(agent, "MEMORY_FILE", tmp_path / "memory.json")
    monkeypatch.setattr(agent, "load_env", lambda: {"GEMINI_API_KEY": "k"})
    monkeypatch.setattr(agent, "github_context", lambda u: "")
    monkeypatch.setattr(agent, "generate", lambda *a: "fixed a flaky test, it was a timezone")
    monkeypatch.setattr(agent, "post", lambda t: (_ for _ in ()).throw(AssertionError("posted")))
    assert agent.main(["agent.py", "--dry-run"]) == 0
    assert "timezone" in capsys.readouterr().out
    assert not (tmp_path / "memory.json").exists()
