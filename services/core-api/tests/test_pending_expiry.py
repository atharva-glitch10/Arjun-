"""A pending yes/no question expires (fix B): a forgotten question must not block the elder forever, and a
"हो" minutes later must not confirm something that was asked long ago."""

from datetime import timedelta

from core_api import models as m
from core_api.db import get_db
from core_api.main import app
from tests.conftest import NOW

PROPOSE = {"action_type": "CREATE_REMINDER", "payload": {"task": "doctor", "date": "2026-10-07", "time": "10:00"}}


def _age(action_id: int, by: timedelta) -> None:
    session = next(app.dependency_overrides[get_db]())
    row = session.get(m.PendingAction, action_id)
    row.created_at = NOW - by
    session.commit()


def _status(action_id: int) -> str:
    session = next(app.dependency_overrides[get_db]())
    return session.get(m.PendingAction, action_id).status


def test_a_fresh_question_is_still_pending(client, uid):
    a = client.post(f"/users/{uid}/actions/propose", json=PROPOSE).json()
    _age(a["id"], timedelta(seconds=90))
    assert client.get(f"/users/{uid}/actions/pending").json()["id"] == a["id"]


def test_an_old_question_is_not_returned_and_is_marked_expired(client, uid):
    a = client.post(f"/users/{uid}/actions/propose", json=PROPOSE).json()
    _age(a["id"], timedelta(minutes=6))
    assert client.get(f"/users/{uid}/actions/pending").json() is None
    assert _status(a["id"]) == "expired"


def test_a_late_yes_cannot_confirm_an_expired_action(client, uid):
    a = client.post(f"/users/{uid}/actions/propose", json=PROPOSE).json()
    _age(a["id"], timedelta(minutes=6))
    assert client.post(f"/users/{uid}/actions/{a['id']}/confirm").status_code == 409
    assert client.get(f"/users/{uid}/reminders").json() == []


def test_only_the_stale_ones_expire(client, uid):
    old = client.post(f"/users/{uid}/actions/propose", json=PROPOSE).json()
    _age(old["id"], timedelta(minutes=20))
    fresh = client.post(f"/users/{uid}/actions/propose", json=PROPOSE).json()
    assert client.get(f"/users/{uid}/actions/pending").json()["id"] == fresh["id"]
