"""Telegram family alerts: queued off the elder's turn, deduplicated, and honest about failure.

httpx is mocked: no test talks to Telegram. The bot token and chat id never appear in a log line.
"""

import pytest
from core_api import telegram


class Resp:
    def __init__(self, ok: bool) -> None:
        self.status_code = 200 if ok else 500
        self._ok = ok

    def json(self) -> dict[str, bool]:
        return {"ok": self._ok}


@pytest.fixture(autouse=True)
def _clean():
    telegram.reset_for_tests()
    yield
    telegram.reset_for_tests()


@pytest.fixture()
def tg(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ENABLED", "1")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")
    monkeypatch.setenv("BASE_URL", "https://example.test")
    monkeypatch.setenv("JOIN_SECRET", "test-secret")
    return telegram


def _capture(monkeypatch, ok: bool = True) -> list[dict]:
    posts: list[dict] = []

    def fake_post(url, json=None, timeout=None):  # noqa: A002 - mirrors httpx.post
        posts.append(json or {})
        return Resp(ok)

    monkeypatch.setattr(telegram.httpx, "post", fake_post)
    return posts


def _notes(client, uid):
    return client.get(f"/users/{uid}/notifications").json()


def _kinds(client, uid):
    return [n["kind"] for n in _notes(client, uid)]


def test_an_emergency_sends_one_alert_with_a_join_button(client, uid, tg, monkeypatch):
    posts = _capture(monkeypatch)
    res = client.post(f"/users/{uid}/distress", params={"kind": "emergency"})
    assert res.json() == {"caregiver_alerted": True}
    telegram.wait_idle()

    assert len(posts) == 1
    assert posts[0]["text"].startswith("🚨")
    assert "तातडीची मदत हवी" in posts[0]["text"]
    button = posts[0]["reply_markup"]["inline_keyboard"][0][0]
    assert button["text"] == telegram.BUTTON
    assert button["url"].startswith("https://example.test/?view=join&t=")
    assert "alert_sent" in _kinds(client, uid)


def test_a_second_emergency_within_ten_minutes_sends_nothing(client, uid, tg, monkeypatch):
    posts = _capture(monkeypatch)
    client.post(f"/users/{uid}/distress", params={"kind": "emergency"})
    telegram.wait_idle()
    client.post(f"/users/{uid}/distress", params={"kind": "emergency"})
    telegram.wait_idle()
    assert len(posts) == 1
    # the newest dashboard alert is honest: it says the last Telegram alert was sent, not that it sent one
    bodies = [n["body"] for n in _notes(client, uid) if n["kind"] == "emergency"]
    assert "Telegram alert sent." in bodies[0]


def test_after_ten_minutes_the_next_alert_is_sent(client, uid, tg, monkeypatch):
    posts = _capture(monkeypatch)
    clock = {"t": 1_000.0}
    monkeypatch.setattr(telegram, "_clock", lambda: clock["t"])
    client.post(f"/users/{uid}/distress", params={"kind": "emergency"})
    telegram.wait_idle()
    clock["t"] += telegram.DEDUPE_S + 1
    client.post(f"/users/{uid}/distress", params={"kind": "emergency"})
    telegram.wait_idle()
    assert len(posts) == 2


def test_telegram_off_sends_nothing_and_the_body_says_so(client, uid, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ENABLED", "0")
    posts = _capture(monkeypatch)
    client.post(f"/users/{uid}/distress", params={"kind": "emergency"})
    telegram.wait_idle()
    assert posts == []
    body = _notes(client, uid)[0]["body"]
    assert "No Telegram alert is set up" in body and "Telegram alert sent" not in body


def test_a_failed_send_is_recorded_and_the_alert_never_claims_delivery(client, uid, tg, monkeypatch):
    _capture(monkeypatch, ok=False)
    res = client.post(f"/users/{uid}/distress", params={"kind": "emergency"})
    assert res.json() == {"caregiver_alerted": True}  # the elder's turn is unchanged
    telegram.wait_idle()

    assert "alert_failed" in _kinds(client, uid)
    body = [n["body"] for n in _notes(client, uid) if n["kind"] == "emergency"][0]
    assert "Telegram alert sent" not in body
    assert "Sending a Telegram alert now" in body


def test_distress_alerts_only_with_consent(client, uid, tg, monkeypatch):
    posts = _capture(monkeypatch)
    client.post(f"/users/{uid}/distress", params={"kind": "distress"})
    telegram.wait_idle()
    assert posts == []

    client.patch(f"/users/{uid}", json={"consent_distress_alert": True})
    client.post(f"/users/{uid}/distress", params={"kind": "distress"})
    telegram.wait_idle()
    assert len(posts) == 1
    assert "बरं वाटत नाहीये" in posts[0]["text"]


def test_a_call_me_request_sends_the_request_text(client, uid, tg, monkeypatch):
    posts = _capture(monkeypatch)
    pending = client.post(
        f"/users/{uid}/actions/propose",
        json={"action_type": "REQUEST_CAREGIVER", "payload": {"message": "Please call me."}},
    ).json()
    client.post(f"/users/{uid}/actions/{pending['id']}/confirm")
    telegram.wait_idle()
    assert len(posts) == 1
    assert posts[0]["text"].startswith("📞")
    assert "बोलायला सांगितलं आहे" in posts[0]["text"]


def test_the_manual_test_endpoint_sends_a_join_link(client, uid, tg, monkeypatch):
    posts = _capture(monkeypatch)
    res = client.post(f"/users/{uid}/alert/test")
    assert res.status_code == 200
    assert res.json()["queued"] is True
    assert res.json()["join_url"].startswith("https://example.test/?view=join&t=")
    telegram.wait_idle()
    assert len(posts) == 1


def test_without_base_url_the_alert_has_no_button(client, uid, tg, monkeypatch):
    monkeypatch.delenv("BASE_URL")
    posts = _capture(monkeypatch)
    client.post(f"/users/{uid}/distress", params={"kind": "emergency"})
    telegram.wait_idle()
    assert len(posts) == 1 and "reply_markup" not in posts[0]
