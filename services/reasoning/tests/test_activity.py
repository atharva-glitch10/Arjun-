"""Every spoken turn tells core-api the time (never the words), for the family's 'Last talked to Arjun' line."""

from datetime import datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from reasoning_svc import main as main_mod
from reasoning_svc.core_client import CoreClient
from reasoning_svc.turn import TurnEngine

NOW = datetime(2026, 10, 6, 9, 0)


@pytest.fixture()
def api(core_http, monkeypatch):
    monkeypatch.setattr(main_mod, "_engine", TurnEngine(CoreClient(core_http), None, clock=lambda: NOW))
    return TestClient(main_mod.app)


def test_a_turn_records_activity_time_only(api, core_http, uid):
    assert core_http.get(f"/users/{uid}/activity").json()["last_seen_at"] is None
    assert api.post("/turn", json={"user_id": uid, "text": "आज काय आहे"}).status_code == 200
    assert core_http.get(f"/users/{uid}/activity").json() == {"last_seen_at": NOW.isoformat(), "how": "voice"}


def test_a_safety_turn_also_counts(api, core_http, uid):
    r = api.post("/turn", json={"user_id": uid, "text": "छातीत दुखतंय"})
    assert r.status_code == 200 and r.json()["intent"] == "EMERGENCY"
    assert core_http.get(f"/users/{uid}/activity").json()["last_seen_at"] == NOW.isoformat()


def test_activity_failure_never_breaks_the_turn(monkeypatch):
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("core-api down")

    core = CoreClient(httpx.Client(transport=httpx.MockTransport(down), base_url="http://core"))
    TurnEngine(core, None, clock=lambda: NOW).note_activity(1)  # logs a warning, does not raise
