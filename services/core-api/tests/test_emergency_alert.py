"""Emergency vs consent (decided 2026-10-24): a physical EMERGENCY always alerts the family on the dashboard,
even when distress-alert consent is off. Emotional DISTRESS stays consent-only (unchanged)."""

from core_api import models as m
from core_api.db import get_db
from core_api.main import app
from sqlalchemy import select


def _notes(client, uid):
    return client.get(f"/users/{uid}/notifications").json()


def _events(uid):
    session = next(app.dependency_overrides[get_db]())
    return list(session.scalars(select(m.DistressEvent).where(m.DistressEvent.user_id == uid)))


def test_emergency_with_consent_off_still_alerts(client, uid):
    r = client.post(f"/users/{uid}/distress", params={"kind": "emergency"})
    assert r.status_code == 201 and r.json() == {"caregiver_alerted": True}
    (note,) = _notes(client, uid)
    assert note["kind"] == "emergency" and "112" in note["body"]
    assert [e.caregiver_alerted for e in _events(uid)] == [True]


def test_distress_with_consent_off_does_not_alert(client, uid):
    assert client.post(f"/users/{uid}/distress", params={"kind": "distress"}).json() == {"caregiver_alerted": False}
    assert client.post(f"/users/{uid}/distress").json() == {"caregiver_alerted": False}  # the old call, unchanged
    assert _notes(client, uid) == []
    assert [e.caregiver_alerted for e in _events(uid)] == [False, False]


def test_distress_with_consent_on_alerts_as_before(client, uid):
    client.patch(f"/users/{uid}", json={"consent_distress_alert": True})
    assert client.post(f"/users/{uid}/distress").json() == {"caregiver_alerted": True}
    assert [n["kind"] for n in _notes(client, uid)] == ["distress"]


def test_emergency_with_consent_on_makes_exactly_one_alert(client, uid):
    client.patch(f"/users/{uid}", json={"consent_distress_alert": True})
    client.post(f"/users/{uid}/distress", params={"kind": "emergency"})
    assert [n["kind"] for n in _notes(client, uid)] == ["emergency"]


def test_the_alert_names_the_configured_family_contacts(client, uid):
    client.post(f"/users/{uid}/contacts", json={"name": "राहुल", "relation": "मुलगा", "phone": "00000 00001"})
    client.post(f"/users/{uid}/contacts", json={"name": "नेहा", "relation": "नात", "phone": "00000 00002"})
    client.post(f"/users/{uid}/distress", params={"kind": "emergency"})
    body = _notes(client, uid)[0]["body"]
    assert "राहुल" in body and "00000 00001" in body and "नेहा" in body


def test_the_alert_says_so_when_no_contact_is_configured(client, uid):
    client.post(f"/users/{uid}/distress", params={"kind": "emergency"})
    assert "No family contact is set up" in _notes(client, uid)[0]["body"]


def test_the_alert_does_not_claim_a_call_or_message_was_sent(client, uid):
    client.post(f"/users/{uid}/distress", params={"kind": "emergency"})
    body = _notes(client, uid)[0]["body"].lower()
    assert "no telegram alert is set up" in body and "telegram alert sent" not in body  # honest: nothing claimed


def test_every_emergency_is_alerted_not_deduplicated(client, uid):
    for _ in range(2):
        client.post(f"/users/{uid}/distress", params={"kind": "emergency"})
    assert [n["kind"] for n in _notes(client, uid)] == ["emergency", "emergency"]


def test_an_unknown_kind_is_rejected(client, uid):
    assert client.post(f"/users/{uid}/distress", params={"kind": "panic"}).status_code == 422
    assert client.post("/users/999/distress", params={"kind": "emergency"}).status_code == 404
