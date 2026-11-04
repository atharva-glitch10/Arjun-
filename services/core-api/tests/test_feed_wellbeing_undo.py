"""Undo after auto-execute, wellbeing (seriousness + mood + summary, no transcript), the live feed, rate limits."""

from datetime import datetime, timedelta

import pytest
from core_api import models as m
from core_api.feed import BROKER, max_severity, notification_severity
from core_api.main import app, get_now
from core_api.ratelimit import RateLimitMiddleware, TokenBucket
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

NOW = datetime(2026, 10, 6, 9, 0)


def _do(client, uid, action_type, payload):
    a = client.post(f"/users/{uid}/actions/propose", json={"action_type": action_type, "payload": payload}).json()
    done = client.post(f"/users/{uid}/actions/{a['id']}/confirm")
    assert done.status_code == 200, done.text
    return done.json()


# ---- undo ----------------------------------------------------------------------------------------------------
def test_undo_removes_an_auto_saved_reminder(client, uid):
    a = _do(client, uid, "CREATE_REMINDER", {"task": "doctor", "date": "2026-10-07", "time": "10:00"})
    assert a["payload"]["_done"]["reminder_id"]
    assert len(client.get(f"/users/{uid}/reminders").json()) == 1
    r = client.post(f"/users/{uid}/actions/{a['id']}/undo")
    assert r.status_code == 200 and r.json()["status"] == "undone"
    assert client.get(f"/users/{uid}/reminders").json() == []
    assert client.post(f"/users/{uid}/actions/{a['id']}/undo").status_code == 409  # only once


def test_undo_is_refused_after_the_window(client, uid):
    a = _do(client, uid, "CREATE_REMINDER", {"task": "doctor", "date": "2026-10-07", "time": "10:00"})
    app.dependency_overrides[get_now] = lambda: NOW + timedelta(minutes=10)
    assert client.post(f"/users/{uid}/actions/{a['id']}/undo").status_code == 409
    assert len(client.get(f"/users/{uid}/reminders").json()) == 1


def test_undo_of_a_help_request_tells_the_family_instead_of_unsending(client, uid):
    a = _do(client, uid, "REQUEST_CAREGIVER", {"message": "Please call me."})
    client.post(f"/users/{uid}/actions/{a['id']}/undo")
    kinds = [n["kind"] for n in client.get(f"/users/{uid}/notifications").json()]
    assert "caregiver_request" in kinds and "help_cancelled" in kinds


def test_undo_reopens_a_completed_reminder(client, uid):
    rem = client.post(f"/users/{uid}/reminders", json={"task": "tea", "date": "2026-10-06", "time": "09:30"}).json()
    a = _do(client, uid, "COMPLETE_REMINDER", {"reminder_id": rem["id"]})
    client.post(f"/users/{uid}/actions/{a['id']}/undo")
    assert client.get(f"/users/{uid}/reminders").json()[0]["status"] == "pending"


# ---- wellbeing -------------------------------------------------------------------------------------------------
def test_wellbeing_today_reports_the_worst_seriousness_and_latest_mood(client, uid):
    assert client.get(f"/users/{uid}/wellbeing/today").json()["severity"] == "normal"
    client.post(f"/users/{uid}/wellbeing", json={"kind": "conversation", "severity": "normal", "mood": "happy",
                                                 "summary": "Talked about her garden.", "turns": 6})
    client.post(f"/users/{uid}/wellbeing", json={"kind": "moment", "severity": "watch", "mood": "lonely",
                                                 "summary": "Said she feels lonely."})
    t = client.get(f"/users/{uid}/wellbeing/today").json()
    assert t["severity"] == "watch" and t["mood"] == "lonely" and t["conversations"] == 1
    assert set(m.Wellbeing.__table__.columns.keys()).isdisjoint({"transcript", "text", "words"})


def test_wellbeing_rejects_unknown_levels(client, uid):
    assert client.post(f"/users/{uid}/wellbeing", json={"severity": "panic"}).status_code == 422
    assert client.post("/users/999/wellbeing", json={}).status_code == 404


# ---- feed ------------------------------------------------------------------------------------------------------
def test_every_notification_and_wellbeing_row_lands_in_the_feed_with_a_level(client, uid):
    client.post(f"/users/{uid}/distress", params={"kind": "emergency"})
    client.post(f"/users/{uid}/wellbeing", json={"severity": "urgent", "mood": "distressed", "summary": "x"})
    rows = client.get(f"/users/{uid}/feed").json()
    assert [(r["kind"], r["severity"]) for r in rows] == [("emergency", "emergency"), ("wellbeing_conversation", "urgent")]
    after = rows[-1]["id"]
    assert client.get(f"/users/{uid}/feed", params={"after": after}).json() == []
    _do(client, uid, "REQUEST_CAREGIVER", {"message": "Please call me."})
    new = client.get(f"/users/{uid}/feed", params={"after": after}).json()
    assert [(r["kind"], r["severity"]) for r in new] == [("caregiver_request", "urgent")]


def test_severity_helpers():
    assert notification_severity("emergency")[0] == "emergency"
    assert notification_severity("reminder")[0] == "info"
    assert max_severity("normal", "watch", "info") == "watch"
    assert max_severity() == "normal"


def test_websocket_pushes_new_rows_and_refuses_a_bad_key(client, uid, monkeypatch):
    with client.websocket_connect(f"/ws/users/{uid}/feed") as ws:
        client.post(f"/users/{uid}/distress", params={"kind": "emergency"})
        msg = ws.receive_json()
        while msg["type"] == "ping":
            msg = ws.receive_json()
        assert msg["type"] == "event" and msg["severity"] == "emergency"
    assert BROKER.count(uid) == 0  # unsubscribed on close
    monkeypatch.setenv("CORE_API_KEY", "secret")
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect(f"/ws/users/{uid}/feed?key=wrong") as ws:
            ws.receive_json()
    assert closed.value.code == 4401


def test_websocket_refuses_the_key_in_the_url_even_when_it_is_right(client, uid, monkeypatch):
    monkeypatch.setenv("CORE_API_KEY", "secret")
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect(f"/ws/users/{uid}/feed?key=secret") as ws:
            ws.receive_json()
    assert closed.value.code == 4401
    with client.websocket_connect(f"/ws/users/{uid}/feed", headers={"x-api-key": "secret"}) as ws:
        client.post(f"/users/{uid}/distress", params={"kind": "emergency"}, headers={"x-api-key": "secret"})
        msg = ws.receive_json()
        while msg["type"] == "ping":
            msg = ws.receive_json()
        assert msg["type"] == "event"


# ---- rate limiting -------------------------------------------------------------------------------------------
def test_token_bucket_allows_a_burst_then_refills():
    t = [0.0]
    b = TokenBucket(rate=2, burst=3, clock=lambda: t[0])
    assert [b.take("a") for _ in range(3)] == [0.0, 0.0, 0.0]
    assert b.take("a") == pytest.approx(0.5)
    assert b.take("b") == 0.0  # per client
    t[0] = 0.5
    assert b.take("a") == 0.0


def test_middleware_answers_429_with_retry_after_and_never_limits_health():
    inner = FastAPI()

    @inner.get("/x")
    def x() -> dict[str, bool]:
        return {"ok": True}

    @inner.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    mw = RateLimitMiddleware(inner, TokenBucket(rate=0.001, burst=2))
    mw.enabled = True
    c = TestClient(mw)
    assert [c.get("/x").status_code for _ in range(3)] == [200, 200, 429]
    r = c.get("/x")
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert c.get("/health").status_code == 200


def test_today_is_never_calmer_than_todays_alerts(client, uid):
    client.post(f"/users/{uid}/distress", params={"kind": "emergency"})
    assert client.get(f"/users/{uid}/wellbeing/today").json()["severity"] == "emergency"
    client.post(f"/users/{uid}/wellbeing", json={"severity": "normal", "mood": "calm", "summary": "Chatted."})
    t = client.get(f"/users/{uid}/wellbeing/today").json()
    assert t["severity"] == "emergency" and t["mood"] == "calm"


def test_row_timestamps_use_the_household_clock_so_actions_do_not_expire_at_once(client, uid, monkeypatch):
    """Regression (2026-10-31): on a UTC machine every proposed action looked 5 h 30 min old and expired."""
    from core_api.deps import local_now

    monkeypatch.setenv("ARJUN_TZ", "Pacific/Kiritimati")  # UTC+14: far from any machine clock
    app.dependency_overrides[get_now] = local_now
    a = client.post(f"/users/{uid}/actions/propose", json={"action_type": "REQUEST_CAREGIVER",
                                                           "payload": {"message": "Please call me."}}).json()
    assert client.post(f"/users/{uid}/actions/{a['id']}/confirm").status_code == 200


# ---- health complaints (task C) ------------------------------------------------------------------------------
def test_a_health_complaint_is_a_watch_note_only_with_consent_once_a_day_per_kind(client, uid):
    assert client.post(f"/users/{uid}/health-complaint", params={"category": "head"}).json() == {"family_told": False}
    assert client.get(f"/users/{uid}/notifications").json() == []  # no consent: nothing is written
    client.patch(f"/users/{uid}", json={"consent_distress_alert": True})
    for _ in range(2):
        assert client.post(f"/users/{uid}/health-complaint", params={"category": "head"}).json() == {"family_told": True}
    client.post(f"/users/{uid}/health-complaint", params={"category": "fever"})
    notes = [n for n in client.get(f"/users/{uid}/notifications").json() if n["kind"] == "health_complaint"]
    assert len(notes) == 2
    assert "headache" in notes[0]["body"] or "headache" in notes[1]["body"]
    assert all("advice" in n["body"] for n in notes)  # says Arjun gave none; never her words
    assert notification_severity("health_complaint")[0] == "watch"


def test_an_unknown_complaint_category_is_refused(client, uid):
    assert client.post(f"/users/{uid}/health-complaint", params={"category": "diagnosis"}).status_code == 422
