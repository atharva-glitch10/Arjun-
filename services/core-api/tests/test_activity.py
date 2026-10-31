"""'Last talked to Arjun': one timestamp per user for the family dashboard. Time only, never words."""

from datetime import datetime, timedelta

from core_api import models as m
from core_api.main import app, get_now

NOW = datetime(2026, 10, 6, 9, 0)  # same fixed clock as conftest

def test_no_activity_yet_is_null(client, uid):
    assert client.get(f"/users/{uid}/activity").json() == {"last_seen_at": None, "how": None}


def test_a_spoken_turn_records_the_time_only(client, uid):
    r = client.post(f"/users/{uid}/activity", json={"how": "voice"})
    assert r.status_code == 200
    assert r.json() == {"last_seen_at": NOW.isoformat(), "how": "voice"}
    assert set(m.Activity.__table__.columns.keys()) == {"id", "user_id", "last_seen_at", "how"}  # no text column


def test_newer_activity_replaces_the_old_one(client, uid):
    client.post(f"/users/{uid}/activity")
    later = NOW + timedelta(minutes=40)
    app.dependency_overrides[get_now] = lambda: later
    client.post(f"/users/{uid}/activity", json={"how": "tap"})
    assert client.get(f"/users/{uid}/activity").json() == {"last_seen_at": later.isoformat(), "how": "tap"}


def test_an_older_report_never_moves_the_time_back(client, uid):
    app.dependency_overrides[get_now] = lambda: NOW + timedelta(minutes=10)
    client.post(f"/users/{uid}/activity")
    app.dependency_overrides[get_now] = lambda: NOW
    client.post(f"/users/{uid}/activity", json={"how": "tap"})
    got = client.get(f"/users/{uid}/activity").json()
    assert got["last_seen_at"] == (NOW + timedelta(minutes=10)).isoformat() and got["how"] == "voice"


def test_unknown_user_and_bad_kind_are_refused(client, uid):
    assert client.get("/users/999/activity").status_code == 404
    assert client.post("/users/999/activity").status_code == 404
    assert client.post(f"/users/{uid}/activity", json={"how": "telepathy"}).status_code == 422


def test_tapping_ok_on_a_card_counts_as_activity(client, uid):
    client.post(f"/users/{uid}/reminders", json={"task": "tea", "date": "2026-10-06", "time": "09:05"})
    app.dependency_overrides[get_now] = lambda: NOW + timedelta(minutes=5, seconds=5)
    client.post("/internal/reminders/fire-due")
    d = client.get(f"/users/{uid}/deliveries/open").json()[0]
    app.dependency_overrides[get_now] = lambda: NOW + timedelta(minutes=7)
    assert client.post(f"/users/{uid}/deliveries/{d['id']}/ack", json={"outcome": "ok"}).status_code == 200
    got = client.get(f"/users/{uid}/activity").json()
    assert got == {"last_seen_at": (NOW + timedelta(minutes=7)).isoformat(), "how": "tap"}
