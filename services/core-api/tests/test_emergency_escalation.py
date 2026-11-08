"""Emergency escalation: family call, help call after no answer, live location only during an emergency."""

import pytest
from core_api import emergency


@pytest.fixture
def calls(monkeypatch):
    placed = []

    def fake(to, message):
        placed.append((to, message))
        return "placed", ""

    monkeypatch.setattr(emergency, "place_call", fake)
    return placed


def _emergency(client, uid):
    assert client.post(f"/users/{uid}/distress", params={"kind": "emergency"}).status_code == 201


def test_location_is_discarded_without_an_emergency(client, uid):
    r = client.post(f"/users/{uid}/emergency/location", json={"lat": 18.52, "lon": 73.85, "accuracy_m": 20})
    assert r.json() == {"kept": False}


def test_location_kept_and_linked_during_an_emergency(client, uid):
    _emergency(client, uid)
    r = client.post(f"/users/{uid}/emergency/location", json={"lat": 18.52, "lon": 73.85, "accuracy_m": 20}).json()
    assert r["kept"] is True and r["maps_url"] == "https://maps.google.com/?q=18.520000,73.850000"


def test_family_then_help_calls_with_address_and_dedupe(client, uid, calls):
    client.post(f"/users/{uid}/contacts", json={"name": "Rahul", "relation": "son", "phone": "98765 43210"})
    client.put(f"/users/{uid}/emergency-settings",
               json={"help_label": "Sunrise nurse desk", "help_phone": "020-1234-5678", "address": "Flat 4, Kothrud, Pune"})
    _emergency(client, uid)
    fam = client.post(f"/internal/users/{uid}/emergency/escalate", json={"stage": "family"}).json()
    assert fam["placed"] == 1 and calls[0][0] == "+919876543210"
    assert client.post(f"/internal/users/{uid}/emergency/escalate", json={"stage": "family"}).json()["deduped"]
    help_ = client.post(f"/internal/users/{uid}/emergency/escalate", json={"stage": "help"}).json()
    assert help_["placed"] == 1 and "Kothrud" in calls[1][1]
    log = client.get(f"/users/{uid}/emergency/calls").json()
    assert {r["stage"] for r in log} == {"family", "help"} and all(r["phone_tail"] for r in log)


def test_no_number_and_disabled_calls_are_recorded_honestly(client, uid, monkeypatch):
    monkeypatch.delenv("CALLS_ENABLED", raising=False)
    client.put(f"/users/{uid}/emergency-settings", json={"help_label": "Desk", "help_phone": "9876543210"})
    _emergency(client, uid)
    r = client.post(f"/internal/users/{uid}/emergency/escalate", json={"stage": "help"}).json()
    assert r["placed"] == 0 and r["calls"][0]["status"] == "skipped_disabled"


def test_bad_help_number_rejected(client, uid):
    assert client.put(f"/users/{uid}/emergency-settings", json={"help_phone": "12"}).status_code == 422


def test_never_dials_112():
    assert emergency.e164("112") == ""
    assert emergency.e164("9876543210") == "+919876543210"
