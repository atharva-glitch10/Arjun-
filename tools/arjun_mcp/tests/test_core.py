import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core  # noqa: E402

ENV = {"CORE_API_KEY": "corekey123456", "SARVAM_API_KEY": "sk_abcdefghijk", "TELEGRAM_BOT_TOKEN": "123456789:" + "A" * 35,
       "ARJUN_ACCESS_CODE": "mango4417", "ARJUN_VOICE_PROVIDER": "sk_wrongvalue1"}


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "env", lambda: dict(ENV))
    monkeypatch.setattr(core, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(core, "ROOT", tmp_path)


def fake(monkeypatch, handler):
    def client(e):
        return httpx.Client(transport=httpx.MockTransport(handler)), "http://core", "http://reasoning"
    monkeypatch.setattr(core, "_client", client)


def test_redact_hides_keys_tokens_and_numbers():
    s = "key corekey123456 sk_zzzzzzzzzz 123456789:" + "B" * 35 + " call +91 98765 43210 mango4417"
    out = core.redact(s, ENV)
    assert "corekey123456" not in out and "sk_zzzz" not in out and "BBBB" not in out and "mango4417" not in out
    assert "98765" not in out and "…3210" in out


def test_health_never_prints_a_wrong_provider_value(monkeypatch):
    fake(monkeypatch, lambda r: httpx.Response(200))
    h = core.health()
    assert h["voice_provider"].startswith("INVALID") and "sk_" not in str(h)
    assert h["access_lock"] == "on"


def test_try_turn_uses_the_test_user_and_refuses_a_real_user_without_confirm(monkeypatch):
    seen = []

    def handler(r):
        seen.append((r.method, r.url.path))
        if r.url.path == "/users":
            return httpx.Response(201, json={"id": 42})
        return httpx.Response(200, json={"reply": "नमस्कार", "intent": "CHAT", "mode": "companion", "source": "llm",
                                         "action": {}, "trace": {"route": "llm"}})
    fake(monkeypatch, handler)
    assert "refused" in core.try_turn("हो", user_id=1)
    out = core.try_turn("नमस्कार")
    assert out["user_id"] == 42 and out["route"] == "llm"
    assert ("POST", "/turn") in seen


def test_write_tools_are_off_by_default():
    assert "refused" in core.add_reminder(1, "उद्या आठ वाजता आठवण कर")


def test_family_tools_drop_transcripts_and_redact(monkeypatch):
    fake(monkeypatch, lambda r: httpx.Response(200, json=[{"title": "Alert", "body": "call 9876543210", "transcript": "x"}]))
    rows = core.feed(1)
    assert rows == [{"title": "Alert", "body": "call …3210"}]


def test_logs_unknown_service_and_missing_file():
    assert core.logs("evil").startswith("unknown service")
    assert core.logs("reasoning") == "no log file"
