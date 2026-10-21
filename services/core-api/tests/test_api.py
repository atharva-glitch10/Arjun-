def _propose(client, uid, action_type, payload):
    return client.post(
        f"/users/{uid}/actions/propose", json={"action_type": action_type, "payload": payload}
    )


def _confirm(client, uid, action_id):
    return client.post(f"/users/{uid}/actions/{action_id}/confirm")


def test_reminder_valid_and_listed_today(client, uid):
    r = client.post(
        f"/users/{uid}/reminders",
        json={"task": "doctor visit", "date": "2026-10-06", "time": "10:00"},
    )
    assert r.status_code == 201
    today = client.get(f"/users/{uid}/reminders/today").json()
    assert [x["task"] for x in today] == ["doctor visit"]


def test_reminder_invalid_input(client, uid):
    r = client.post(f"/users/{uid}/reminders", json={"task": "", "date": "nope", "time": "25:00"})
    assert r.status_code == 422


def test_reminder_ambiguous_time_rejected(client, uid):
    r = client.post(
        f"/users/{uid}/reminders",
        json={"task": "medicine", "date": "2026-10-07", "time": "08:00", "time_ambiguous": True},
    )
    assert r.status_code == 422
    assert "ambiguous" in r.json()["detail"]


def test_reminder_in_past_rejected(client, uid):
    r = client.post(
        f"/users/{uid}/reminders", json={"task": "x", "date": "2026-10-05", "time": "08:00"}
    )
    assert r.status_code == 422


def test_unknown_user_404(client):
    assert client.get("/users/999").status_code == 404


def test_bad_user_time_rejected(client):
    assert client.post("/users", json={"name": "A", "wake_time": "7am"}).status_code == 422


def test_propose_confirm_creates_reminder_only_after_confirmation(client, uid):
    payload = {"task": "bp check", "date": "2026-10-07", "time": "07:30"}
    p = _propose(client, uid, "CREATE_REMINDER", payload)
    assert p.status_code == 201
    assert client.get(f"/users/{uid}/reminders").json() == []  # not saved yet
    pend = client.get(f"/users/{uid}/actions/pending").json()
    assert pend["id"] == p.json()["id"]
    assert _confirm(client, uid, pend["id"]).status_code == 200
    assert len(client.get(f"/users/{uid}/reminders").json()) == 1
    assert _confirm(client, uid, pend["id"]).status_code == 409


def test_propose_reject_discards(client, uid):
    payload = {"task": "walk", "date": "2026-10-07", "time": "07:00"}
    p = _propose(client, uid, "CREATE_REMINDER", payload)
    client.post(f"/users/{uid}/actions/{p.json()['id']}/reject")
    assert client.get(f"/users/{uid}/reminders").json() == []
    assert client.get(f"/users/{uid}/actions/pending").json() is None


def test_propose_missing_or_ambiguous_slots_rejected(client, uid):
    missing = _propose(client, uid, "CREATE_REMINDER", {"task": "x", "date": "2026-10-07"})
    assert missing.status_code == 422
    amb = {"task": "x", "date": "2026-10-07", "time": "08:00", "time_ambiguous": True}
    assert _propose(client, uid, "CREATE_REMINDER", amb).status_code == 422


def test_complete_reminder_flow(client, uid):
    rid = client.post(
        f"/users/{uid}/reminders", json={"task": "medicine", "date": "2026-10-06", "time": "20:00"}
    ).json()["id"]
    assert _propose(client, uid, "COMPLETE_REMINDER", {"reminder_id": 12345}).status_code == 422
    p = _propose(client, uid, "COMPLETE_REMINDER", {"reminder_id": rid})
    _confirm(client, uid, p.json()["id"])
    assert client.get(f"/users/{uid}/reminders").json()[0]["status"] == "done"


def test_appointments_next(client, uid):
    client.post(
        f"/users/{uid}/appointments",
        json={"title": "Eye doctor", "starts_at": "2026-10-09T11:00:00", "location": "Clinic"},
    )
    assert client.get(f"/users/{uid}/appointments/next").json()["title"] == "Eye doctor"


def test_stories_private_by_default_and_shared_only_on_confirm(client, uid):
    p = _propose(client, uid, "SAVE_STORY", {"summary": "A village story"})
    _confirm(client, uid, p.json()["id"])
    assert client.get(f"/users/{uid}/memory-book").json() == []  # private
    sid = client.get(f"/users/{uid}/stories/latest").json()["id"]
    p = _propose(client, uid, "SHARE_STORY", {"story_id": sid})
    assert client.get(f"/users/{uid}/memory-book").json() == []  # proposal alone shares nothing
    _confirm(client, uid, p.json()["id"])
    assert len(client.get(f"/users/{uid}/memory-book").json()) == 1


def test_forget_story_deletes(client, uid):
    sid = client.post(f"/users/{uid}/stories", json={"summary": "secret"}).json()["id"]
    assert client.delete(f"/users/{uid}/stories/{sid}").status_code == 204
    assert client.get(f"/users/{uid}/stories/latest").json() is None
    assert client.delete(f"/users/{uid}/stories/{sid}").status_code == 404


def test_distress_alerts_caregiver_only_with_consent(client, uid):
    assert client.post(f"/users/{uid}/distress").json() == {"caregiver_alerted": False}
    assert client.get(f"/users/{uid}/notifications").json() == []
    client.patch(f"/users/{uid}", json={"consent_distress_alert": True})
    assert client.post(f"/users/{uid}/distress").json() == {"caregiver_alerted": True}
    assert client.get(f"/users/{uid}/notifications").json()[0]["kind"] == "distress"


def test_caregiver_request_and_decline_gate(client, uid):
    p = _propose(client, uid, "REQUEST_CAREGIVER", {"message": "Please call"})
    _confirm(client, uid, p.json()["id"])
    assert client.get(f"/users/{uid}/caregiver-requests").json()[0]["message"] == "Please call"
    assert client.get(f"/users/{uid}/opener-allowed").json() == {"allowed": False}  # 09:00 < 10:00
    client.patch(f"/users/{uid}", json={"opener_start": "08:00"})
    assert client.get(f"/users/{uid}/opener-allowed").json() == {"allowed": True}
    client.post(f"/users/{uid}/declines")
    assert client.get(f"/users/{uid}/opener-allowed").json() == {"allowed": False}


def test_fire_due_marks_reminders(client, uid):
    client.post(
        f"/users/{uid}/reminders", json={"task": "tea", "date": "2026-10-06", "time": "09:00"}
    )
    assert [f["task"] for f in client.post("/internal/reminders/fire-due").json()] == ["tea"]
    assert client.post("/internal/reminders/fire-due").json() == []


def test_api_key_enforced(client, uid, monkeypatch):
    monkeypatch.setenv("CORE_API_KEY", "secret")
    assert client.get(f"/users/{uid}").status_code == 401
    assert client.get(f"/users/{uid}", headers={"X-API-Key": "secret"}).status_code == 200
