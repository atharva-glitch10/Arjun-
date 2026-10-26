"""The /delivery/* and /session/*/busy endpoints the voice agent uses (the agent never talks to core-api)."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from reasoning_svc import main as main_mod
from reasoning_svc.core_client import CoreClient
from reasoning_svc.turn import TurnEngine

NOW = datetime(2026, 10, 6, 9, 0)


@pytest.fixture()
def api(core_http, uid, monkeypatch):
    from core_api.main import app as core_app
    from core_api.main import get_now

    monkeypatch.setattr(main_mod, "_engine", TurnEngine(CoreClient(core_http), None, clock=lambda: NOW))
    core_app.dependency_overrides[get_now] = lambda: NOW
    core_http.post(f"/users/{uid}/reminders", json={"task": "tea", "date": "2026-10-06", "time": "09:05"})
    core_app.dependency_overrides[get_now] = lambda: NOW + timedelta(minutes=5, seconds=5)
    core_http.post("/internal/reminders/fire-due")
    return TestClient(main_mod.app)


def test_next_returns_the_rendered_item_then_nothing_for_a_second_session(api, uid):
    first = api.post("/delivery/next", json={"user_id": uid, "session": "A"})
    assert first.status_code == 200
    body = first.json()
    assert body["text"] == "आठवण: tea." and body["screen"] == "reminder" and body["item"].startswith("reminder:")
    assert api.post("/delivery/next", json={"user_id": uid, "session": "B"}).json() is None


def test_spoken_and_release_are_no_content_and_wrong_sessions_are_refused(api, uid):
    d = api.post("/delivery/next", json={"user_id": uid, "session": "A"}).json()
    base = f"/delivery/{d['delivery_id']}"
    assert api.post(f"{base}/spoken", json={"user_id": uid, "session": "B"}).status_code == 409
    assert api.post(f"{base}/release", json={"user_id": uid, "session": "A", "reason": "tts"}).status_code == 204
    again = api.post("/delivery/next", json={"user_id": uid, "session": "A"}).json()
    assert api.post(f"/delivery/{again['delivery_id']}/spoken", json={"user_id": uid, "session": "A"}).status_code == 204


def test_busy_reports_the_three_reasons_not_to_speak_or_close(api, uid):
    assert api.get(f"/session/{uid}/busy").json() == {"pending": False, "safety_hold": False, "queued": 1}


def test_unknown_user_is_not_a_server_error(api):
    assert api.post("/delivery/next", json={"user_id": 999, "session": "A"}).status_code == 404
