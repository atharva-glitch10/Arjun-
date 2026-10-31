"""Meal check-ins: the family switches them on; the scheduler asks at the family-set meal time; the elder's answer
(done / skipped) is recorded exactly as self-reported and the family sees one plain line. No scores, no nagging."""

from datetime import datetime, timedelta

from core_api.main import app, get_now

NOW = datetime(2026, 10, 6, 9, 0)


def _clock(start):
    box = {"now": start}
    app.dependency_overrides[get_now] = lambda: box["now"]
    return box


def _user(client, **over):
    body = {
        "name": "Heerabai (synthetic)",
        "language": "mr",
        "honorific": "Heerabai",
        "daily_checkins": True,
        "breakfast_time": "08:00",
        "lunch_time": "13:00",
        "snack_time": "17:00",
    }
    body.update(over)
    r = client.post("/users", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _tick(client, box, at):
    box["now"] = at
    r = client.post("/internal/checkins/tick")
    assert r.status_code == 200, r.text
    return r.json()


def _all(client, uid):
    return client.get(f"/users/{uid}/checkins").json()


def _deliveries(client, uid):
    return client.get(f"/users/{uid}/deliveries").json()


def test_the_tick_asks_only_the_meal_that_is_due_and_never_twice(client):
    uid = _user(client)
    box = _clock(NOW)

    out = _tick(client, box, NOW)
    assert [(x["kind"], x["user_id"]) for x in out["asked"]] == [("breakfast", uid)]
    assert out["followed_up"] == [] and out["closed"] == []
    meals = {c["kind"]: c["status"] for c in _all(client, uid)}
    assert meals == {"breakfast": "asked", "lunch": "pending", "snack": "pending"}

    again = _tick(client, box, NOW)
    assert again == {"asked": [], "followed_up": [], "closed": []}
    d = _deliveries(client, uid)
    assert [(x["kind"], x["attempt"], x["label"], x["status"]) for x in d] == [
        ("checkin", 1, "breakfast", "queued")
    ]
    assert client.get(f"/users/{uid}/checkins/open").json()["kind"] == "breakfast"


def test_no_rows_and_no_prompts_when_the_family_switched_checkins_off(client):
    uid = _user(client, daily_checkins=False, breakfast_time="09:00")
    box = _clock(NOW)
    assert _tick(client, box, NOW) == {"asked": [], "followed_up": [], "closed": []}
    assert _all(client, uid) == []
    assert _deliveries(client, uid) == []
    assert client.get(f"/users/{uid}/checkins/open").json() is None


def test_a_done_answer_is_recorded_and_the_family_sees_one_plain_line(client):
    uid = _user(client)
    box = _clock(NOW)
    _tick(client, box, NOW)
    open_row = client.get(f"/users/{uid}/checkins/open").json()

    r = client.post(f"/users/{uid}/checkins/{open_row['id']}/answer", json={"answer": "done"})
    assert r.status_code == 200 and r.json()["status"] == "done" and r.json()["answered_at"]
    assert client.get(f"/users/{uid}/checkins/open").json() is None

    notes = client.get(f"/users/{uid}/notifications").json()
    assert [n["kind"] for n in notes] == ["checkin"]
    assert "breakfast" in notes[0]["body"].lower() and "done" in notes[0]["body"].lower()
    feed = client.get(f"/users/{uid}/feed").json()
    assert feed[-1]["kind"] == "checkin" and feed[-1]["severity"] == "info"
    # the queued prompt is finished, not left for a voice session to speak after the answer
    assert _deliveries(client, uid)[0]["status"] in ("acknowledged", "superseded")


def test_a_skipped_answer_is_recorded_neutrally_without_advice(client):
    uid = _user(client)
    box = _clock(NOW)
    _tick(client, box, NOW)
    cid = client.get(f"/users/{uid}/checkins/open").json()["id"]
    r = client.post(f"/users/{uid}/checkins/{cid}/answer", json={"answer": "skipped"})
    assert r.status_code == 200 and r.json()["status"] == "skipped"
    body = client.get(f"/users/{uid}/notifications").json()[0]["body"]
    assert "skipped" in body.lower()
    assert not any(word in body.lower() for word in ("should", "must", "advice", "healthy"))


def test_one_follow_up_after_thirty_minutes_and_never_a_third_ask(client):
    uid = _user(client, breakfast_time="09:00")
    box = _clock(NOW)
    _tick(client, box, NOW)
    assert _tick(client, box, NOW + timedelta(minutes=29))["followed_up"] == []
    out = _tick(client, box, NOW + timedelta(minutes=30))
    assert [x["kind"] for x in out["followed_up"]] == ["breakfast"]
    assert _tick(client, box, NOW + timedelta(minutes=31))["followed_up"] == []
    assert _tick(client, box, NOW + timedelta(minutes=59))["followed_up"] == []
    attempts = [(d["attempt"], d["status"]) for d in _deliveries(client, uid)]
    assert attempts == [(1, "superseded"), (2, "queued")]
    assert _all(client, uid)[0]["followups"] == 1


def test_an_answer_stops_the_follow_up(client):
    uid = _user(client, breakfast_time="09:00")
    box = _clock(NOW)
    _tick(client, box, NOW)
    cid = client.get(f"/users/{uid}/checkins/open").json()["id"]
    box["now"] = NOW + timedelta(minutes=10)
    assert client.post(f"/users/{uid}/checkins/{cid}/answer", json={"answer": "done"}).status_code == 200
    assert _tick(client, box, NOW + timedelta(minutes=30))["followed_up"] == []
    assert len(_deliveries(client, uid)) == 1


def test_a_meal_that_waited_hours_is_not_asked_at_all(client):
    uid = _user(client, breakfast_time="07:00")
    box = _clock(NOW)
    out = _tick(client, box, NOW)  # two hours late
    assert [x["kind"] for x in out["closed"]] == ["breakfast"]
    assert out["asked"] == []
    assert _deliveries(client, uid) == []
    assert _all(client, uid)[0]["status"] == "missed"


def test_only_an_asked_checkin_can_be_answered_and_only_by_its_own_family(client):
    uid = _user(client)
    box = _clock(NOW)
    _tick(client, box, NOW)
    lunch = [c for c in _all(client, uid) if c["kind"] == "lunch"][0]
    assert client.post(f"/users/{uid}/checkins/{lunch['id']}/answer", json={"answer": "done"}).status_code == 409

    other = _user(client, name="Other (synthetic)")
    breakfast = [c for c in _all(client, uid) if c["kind"] == "breakfast"][0]
    assert client.post(f"/users/{other}/checkins/{breakfast['id']}/answer", json={"answer": "done"}).status_code == 404


def test_the_open_checkin_says_whether_a_prompt_was_really_heard(client):
    uid = _user(client)
    box = _clock(NOW)
    _tick(client, box, NOW)
    assert client.get(f"/users/{uid}/checkins/open").json()["heard"] is False
    d = client.get(f"/users/{uid}/deliveries/next").json()
    base = f"/users/{uid}/deliveries/{d['id']}"
    client.post(f"{base}/claim", json={"session": "A"})
    client.post(f"{base}/spoken", json={"session": "A"})
    assert client.get(f"/users/{uid}/checkins/open").json()["heard"] is True


def test_an_answer_that_is_not_done_or_skipped_is_rejected(client):
    uid = _user(client)
    box = _clock(NOW)
    _tick(client, box, NOW)
    cid = client.get(f"/users/{uid}/checkins/open").json()["id"]
    assert client.post(f"/users/{uid}/checkins/{cid}/answer", json={"answer": "later"}).status_code == 422
