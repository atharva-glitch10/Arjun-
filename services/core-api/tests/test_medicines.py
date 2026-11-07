from datetime import datetime, timedelta

from core_api.main import app, get_now

NOW = datetime(2026, 10, 6, 9, 0)  # same as conftest.NOW


def _add(client, uid, **over):
    body = {"name": "Telma AM", "dose": "[dose as entered]", "anchor": "fixed", "time": "09:30"}
    body.update(over)
    return client.post(f"/users/{uid}/medicines", json=body)


def _clock(start: datetime):
    box = {"now": start}
    app.dependency_overrides[get_now] = lambda: box["now"]
    return box


# ---- family CRUD / validation ----------------------------------------------------------------
def test_create_and_list_keeps_name_and_dose_verbatim(client, uid):
    r = _add(client, uid, name="  Telma AM ", dose="1 tablet (40 mg)")
    assert r.status_code == 201
    got = client.get(f"/users/{uid}/medicines").json()
    assert got[0]["name"] == "Telma AM" and got[0]["dose"] == "1 tablet (40 mg)"


def test_fixed_anchor_requires_time(client, uid):
    assert _add(client, uid, time=None).status_code == 422


def test_bad_inputs_rejected(client, uid):
    assert _add(client, uid, name="  ").status_code == 422
    assert _add(client, uid, time="9:30").status_code == 422
    assert _add(client, uid, photo_url="javascript:alert(1)").status_code == 422
    assert _add(client, uid, max_reminders=0).status_code == 422
    assert client.post("/users/999/medicines", json={"name": "x", "dose": "y", "time": "09:00"}).status_code == 404


def test_meal_anchor_uses_family_time_plus_offset(client, uid):
    client.patch(f"/users/{uid}", json={"lunch_time": "13:00"})
    _add(client, uid, name="Lunch med", anchor="lunch", time=None, offset_min=30)
    doses = client.get(f"/users/{uid}/medicine-doses").json()
    assert doses[0]["due_at"].startswith("2026-10-06T13:30")


def test_patch_revalidates_and_resets_untouched_dose(client, uid):
    mid = _add(client, uid, time="09:30").json()["id"]
    assert client.get(f"/users/{uid}/medicine-doses").json()[0]["due_at"].endswith("09:30:00")
    # switching to a fixed anchor without a time is invalid
    assert client.patch(f"/users/{uid}/medicines/{mid}", json={"time": None}).status_code == 422
    r = client.patch(f"/users/{uid}/medicines/{mid}", json={"time": "10:15"})
    assert r.status_code == 200
    assert client.get(f"/users/{uid}/medicine-doses").json()[0]["due_at"].endswith("10:15:00")


def test_delete_medicine_removes_doses(client, uid):
    mid = _add(client, uid).json()["id"]
    client.get(f"/users/{uid}/medicine-doses")
    assert client.delete(f"/users/{uid}/medicines/{mid}").status_code == 204
    assert client.get(f"/users/{uid}/medicine-doses").json() == []
    assert client.delete(f"/users/{uid}/medicines/{mid}").status_code == 404


def test_deactivating_withdraws_open_doses_and_stops_reminders(client, uid):
    box = _clock(NOW - timedelta(hours=3))
    mid = _add(client, uid, time="09:00").json()["id"]
    box["now"] = NOW
    assert len(client.post("/internal/medicines/tick").json()["reminded"]) == 1  # already reminded
    r = client.patch(f"/users/{uid}/medicines/{mid}", json={"active": False})
    assert r.status_code == 200 and r.json()["active"] is False
    assert client.get(f"/users/{uid}/medicine-doses").json() == []
    assert client.get(f"/users/{uid}/deliveries/open").json() == []
    box["now"] = NOW + timedelta(minutes=15)
    assert client.post("/internal/medicines/tick").json() == {"reminded": [], "unconfirmed": []}


def test_deactivating_keeps_a_dose_already_taken(client, uid):
    box = _clock(NOW - timedelta(hours=3))
    mid = _add(client, uid, time="09:00").json()["id"]
    box["now"] = NOW
    dose_id = client.get(f"/users/{uid}/medicines/due").json()["current"][0]["id"]
    client.post(f"/users/{uid}/medicine-doses/{dose_id}/taken")
    assert client.patch(f"/users/{uid}/medicines/{mid}", json={"active": False}).status_code == 200
    doses = client.get(f"/users/{uid}/medicine-doses").json()
    assert [d["status"] for d in doses] == ["taken"]  # history is not rewritten


def test_medicine_added_after_its_time_has_no_dose_today(client, uid):
    _add(client, uid, time="07:00")  # NOW is 09:00 -> already passed when created
    assert client.get(f"/users/{uid}/medicine-doses").json() == []


# ---- elder: due / taken / snooze --------------------------------------------------------------
def test_due_taken_is_self_reported_with_on_time_flag(client, uid):
    box = _clock(NOW - timedelta(hours=3))
    _add(client, uid, time="09:00")  # created at 06:00 -> dose due 09:00 today
    box["now"] = NOW + timedelta(minutes=10)  # 09:10
    due = client.get(f"/users/{uid}/medicines/due").json()
    assert [d["name"] for d in due["current"]] == ["Telma AM"]
    assert due["current"][0]["dose"] == "[dose as entered]"
    dose_id = due["current"][0]["id"]

    r = client.post(f"/users/{uid}/medicine-doses/{dose_id}/taken")
    assert r.status_code == 200 and r.json()["status"] == "taken" and r.json()["on_time"] is True
    assert client.get(f"/users/{uid}/medicines/due").json()["current"] == []
    assert client.post(f"/users/{uid}/medicine-doses/{dose_id}/taken").status_code == 409


def test_late_take_is_flagged_late_not_punished(client, uid):
    box = _clock(NOW - timedelta(hours=3))
    _add(client, uid, time="09:00", window_min=30)
    box["now"] = NOW + timedelta(minutes=45)  # 09:45
    dose_id = client.get(f"/users/{uid}/medicines/due").json()["current"][0]["id"]
    assert client.post(f"/users/{uid}/medicine-doses/{dose_id}/taken").json()["on_time"] is False


def test_snooze_hides_dose_until_time_then_caps(client, uid):
    box = _clock(NOW - timedelta(hours=3))
    _add(client, uid, time="09:00", max_reminders=2)
    box["now"] = NOW + timedelta(minutes=1)
    dose_id = client.get(f"/users/{uid}/medicines/due").json()["current"][0]["id"]
    r = client.post(f"/users/{uid}/medicine-doses/{dose_id}/snooze")
    assert r.status_code == 200
    assert client.get(f"/users/{uid}/medicines/due").json()["current"] == []
    box["now"] += timedelta(minutes=16)
    assert len(client.get(f"/users/{uid}/medicines/due").json()["current"]) == 1
    assert client.post(f"/users/{uid}/medicine-doses/{dose_id}/snooze").status_code == 200
    assert client.post(f"/users/{uid}/medicine-doses/{dose_id}/snooze").status_code == 409


# ---- scheduler tick: reminders then family-only notice ----------------------------------------
def test_tick_reminds_then_notifies_family_once(client, uid):
    box = _clock(NOW - timedelta(hours=3))
    _add(client, uid, time="09:00", max_reminders=2, repeat_minutes=15)
    box["now"] = NOW  # 09:00
    t = client.post("/internal/medicines/tick").json()
    assert [x["reminder_no"] for x in t["reminded"]] == [1] and t["unconfirmed"] == []
    assert client.post("/internal/medicines/tick").json()["reminded"] == []  # too soon

    box["now"] = NOW + timedelta(minutes=15)
    assert [x["reminder_no"] for x in client.post("/internal/medicines/tick").json()["reminded"]] == [2]

    box["now"] = NOW + timedelta(minutes=30)
    t = client.post("/internal/medicines/tick").json()
    assert t["reminded"] == [] and len(t["unconfirmed"]) == 1
    notes = client.get(f"/users/{uid}/notifications").json()
    assert [n["kind"] for n in notes] == ["medicine_unconfirmed"]
    assert "cannot tell" in notes[0]["body"]

    box["now"] = NOW + timedelta(minutes=60)  # nothing more: no repeat nags, no second notice
    t = client.post("/internal/medicines/tick").json()
    assert t == {"reminded": [], "unconfirmed": []}
    assert len(client.get(f"/users/{uid}/notifications").json()) == 1


def test_taken_dose_is_not_reminded(client, uid):
    box = _clock(NOW - timedelta(hours=3))
    _add(client, uid, time="09:00")
    box["now"] = NOW
    dose_id = client.get(f"/users/{uid}/medicines/due").json()["current"][0]["id"]
    client.post(f"/users/{uid}/medicine-doses/{dose_id}/taken")
    assert client.post("/internal/medicines/tick").json() == {"reminded": [], "unconfirmed": []}


# ---- boundary: the voice/propose path cannot create or edit medicines -------------------------
def test_propose_cannot_create_or_edit_medicines(client, uid):
    for action in ("CREATE_MEDICINE", "EDIT_MEDICINE", "DELETE_MEDICINE", "ADD_MEDICINE"):
        r = client.post(
            f"/users/{uid}/actions/propose",
            json={"action_type": action, "payload": {"name": "x", "dose": "y"}},
        )
        assert r.status_code == 422
    assert client.get(f"/users/{uid}/medicines").json() == []


def test_voice_taken_needs_confirmation_and_quotes_sql_text(client, uid):
    box = _clock(NOW - timedelta(hours=3))
    _add(client, uid, time="09:00", name="Telma AM", dose="[dose]")
    box["now"] = NOW
    dose_id = client.get(f"/users/{uid}/medicines/due").json()["current"][0]["id"]
    p = client.post(
        f"/users/{uid}/actions/propose",
        json={"action_type": "MEDICINE_TAKEN", "payload": {"dose_id": dose_id}},
    )
    assert p.status_code == 201
    assert p.json()["payload"]["name"] == "Telma AM" and p.json()["payload"]["dose"] == "[dose]"
    # proposing alone changes nothing
    assert len(client.get(f"/users/{uid}/medicines/due").json()["current"]) == 1
    assert client.post(f"/users/{uid}/actions/{p.json()['id']}/confirm").status_code == 200
    assert client.get(f"/users/{uid}/medicines/due").json()["current"] == []


def test_propose_taken_unknown_dose_rejected(client, uid):
    r = client.post(
        f"/users/{uid}/actions/propose",
        json={"action_type": "MEDICINE_TAKEN", "payload": {"dose_id": 999}},
    )
    assert r.status_code in (404, 422)
