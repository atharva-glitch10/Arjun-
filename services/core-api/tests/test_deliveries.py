"""T8 step 1: the delivery queue. A due reminder or medicine prompt becomes a queued delivery; a voice session claims
it ATOMICALLY, and it is "spoken" only after playback really finished. Nothing is silently dropped.
"""

import threading
from datetime import datetime, timedelta

from core_api import models as m
from core_api.db import Base, get_db
from core_api.deliveries import claim_delivery
from core_api.main import app, get_now
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

NOW = datetime(2026, 10, 6, 9, 0)


def _clock(start):
    box = {"now": start}
    app.dependency_overrides[get_now] = lambda: box["now"]
    return box


def _reminder(client, uid, hhmm="09:05", task="tea"):
    r = client.post(f"/users/{uid}/reminders", json={"task": task, "date": "2026-10-06", "time": hhmm})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _fire(client, box, at):
    box["now"] = at
    return client.post("/internal/reminders/fire-due").json()


def _sweep(client, box, at):
    box["now"] = at
    return client.post("/internal/deliveries/sweep").json()


def _all(client, uid):
    return client.get(f"/users/{uid}/deliveries").json()


def _session():
    return next(app.dependency_overrides[get_db]())


# ---- queueing ---------------------------------------------------------------------------------------------
def test_fire_due_queues_one_delivery_per_reminder_and_never_twice(client, uid):
    box = _clock(NOW)
    rid = _reminder(client, uid)
    _fire(client, box, NOW + timedelta(minutes=5, seconds=10))
    _fire(client, box, NOW + timedelta(minutes=5, seconds=40))  # a second tick must not queue it again
    got = _all(client, uid)
    assert [(d["kind"], d["ref_id"], d["status"], d["label"]) for d in got] == [("reminder", rid, "queued", "tea")]


def _med(client, uid, **over):
    body = {"name": "Telma AM", "dose": "[dose as entered]", "anchor": "fixed", "time": "09:00"}
    body.update(over)
    return client.post(f"/users/{uid}/medicines", json=body).json()["id"]


def test_medicine_tick_queues_each_reminder_with_its_attempt_number(client, uid):
    box = _clock(NOW - timedelta(hours=3))
    _med(client, uid, max_reminders=3, repeat_minutes=15)
    box["now"] = NOW
    client.post("/internal/medicines/tick")
    client.post("/internal/medicines/tick")  # too soon: no second delivery
    d = _all(client, uid)
    assert [(x["kind"], x["attempt"], x["label"], x["detail"]) for x in d] == [
        ("medicine", 1, "Telma AM", "[dose as entered]")
    ]


def test_an_unspoken_older_medicine_delivery_is_replaced_by_the_newer_one(client, uid):
    box = _clock(NOW - timedelta(hours=3))
    _med(client, uid, max_reminders=3, repeat_minutes=15)
    box["now"] = NOW
    client.post("/internal/medicines/tick")
    box["now"] = NOW + timedelta(minutes=15)
    client.post("/internal/medicines/tick")
    _sweep(client, box, NOW + timedelta(minutes=15))
    status = {x["attempt"]: x["status"] for x in _all(client, uid)}
    assert status == {1: "superseded", 2: "queued"}


# ---- claiming: atomic, one speaker only -------------------------------------------------------------------
def _queued(client, uid, box):
    _reminder(client, uid)
    _fire(client, box, NOW + timedelta(minutes=5, seconds=5))
    return client.get(f"/users/{uid}/deliveries/next").json()


def test_next_returns_the_oldest_waiting_delivery_or_nothing(client, uid):
    box = _clock(NOW)
    assert client.get(f"/users/{uid}/deliveries/next").json() is None
    _reminder(client, uid, "09:05", "first")
    _reminder(client, uid, "09:06", "second")
    _fire(client, box, NOW + timedelta(minutes=6, seconds=10))
    assert client.get(f"/users/{uid}/deliveries/next").json()["label"] == "first"
    assert client.get(f"/users/{uid}/deliveries/waiting").json() == {"queued": 2}


def test_a_second_session_cannot_claim_what_the_first_holds(client, uid):
    box = _clock(NOW)
    d = _queued(client, uid, box)
    base = f"/users/{uid}/deliveries/{d['id']}"
    assert client.post(f"{base}/claim", json={"session": "A"}).status_code == 200
    assert client.post(f"{base}/claim", json={"session": "B"}).status_code == 409
    assert client.get(f"/users/{uid}/deliveries/next").json() is None  # a claimed item is not offered again


def test_many_sessions_racing_for_one_item_produce_exactly_one_winner(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'race.db'}", connect_args={"timeout": 30, "check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(m.User(id=1, name="Demo (synthetic)"))
        s.flush()
        s.add(m.Delivery(user_id=1, kind="reminder", ref_id=1, attempt=1, due_at=NOW, status="queued"))
        s.commit()
    wins, errors, barrier = [], [], threading.Barrier(8)

    def go(i):
        try:
            with Session(engine) as s:
                barrier.wait()
                wins.append(claim_delivery(s, 1, 1, f"s{i}", NOW))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=go, args=(i,)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors and sorted(wins) == [False] * 7 + [True]
    with Session(engine) as s:
        assert s.scalar(select(m.Delivery.status)) == "speaking"


# ---- spoken only after playback completed ---------------------------------------------------------------------
def test_spoken_needs_a_claim_by_the_same_session(client, uid):
    box = _clock(NOW)
    d = _queued(client, uid, box)
    base = f"/users/{uid}/deliveries/{d['id']}"
    assert client.post(f"{base}/spoken", json={"session": "A"}).status_code == 409  # never claimed
    client.post(f"{base}/claim", json={"session": "A"})
    assert client.post(f"{base}/spoken", json={"session": "B"}).status_code == 409  # someone else's
    r = client.post(f"{base}/spoken", json={"session": "A"})
    assert r.status_code == 200 and r.json()["status"] == "spoken" and r.json()["spoken_at"]
    assert client.post(f"{base}/spoken", json={"session": "A"}).status_code == 409  # not twice


def test_a_failed_tts_leaves_it_undelivered_and_the_dashboard_can_say_so(client, uid):
    box = _clock(NOW)
    d = _queued(client, uid, box)
    base = f"/users/{uid}/deliveries/{d['id']}"
    for n in range(1, 4):
        client.post(f"{base}/claim", json={"session": "A"})
        r = client.post(f"{base}/release", json={"session": "A", "reason": "tts"})
        assert r.json()["fail_count"] == n
    final = _all(client, uid)[0]
    assert final["status"] == "undelivered" and final["spoken_at"] is None
    kinds = [n["kind"] for n in client.get(f"/users/{uid}/notifications").json()]
    assert "undelivered" in kinds


def test_an_interrupted_delivery_goes_back_to_the_queue_without_counting_as_a_failure(client, uid):
    box = _clock(NOW)
    d = _queued(client, uid, box)
    base = f"/users/{uid}/deliveries/{d['id']}"
    for _ in range(5):
        client.post(f"{base}/claim", json={"session": "A"})
        r = client.post(f"{base}/release", json={"session": "A", "reason": "interrupted"})
        assert r.json()["status"] == "queued" and r.json()["fail_count"] == 0


def test_a_crashed_session_does_not_hold_an_item_forever(client, uid):
    box = _clock(NOW)
    d = _queued(client, uid, box)
    client.post(f"/users/{uid}/deliveries/{d['id']}/claim", json={"session": "crashed"})
    _sweep(client, box, box["now"] + timedelta(minutes=5))
    assert _all(client, uid)[0]["status"] == "queued"
    assert client.post(f"/users/{uid}/deliveries/{d['id']}/claim", json={"session": "B"}).status_code == 200


# ---- nothing is silently dropped ------------------------------------------------------------------------------
def test_more_than_three_late_items_are_spoken_newest_three_and_the_rest_stay_visible(client, uid):
    box = _clock(NOW)
    for i in range(5):
        _reminder(client, uid, f"09:0{i + 1}", f"task{i}")
    _fire(client, box, NOW + timedelta(minutes=30))
    _sweep(client, box, NOW + timedelta(minutes=30))
    by_label = {d["label"]: d["status"] for d in _all(client, uid)}
    assert by_label == {"task0": "shown_only", "task1": "shown_only", "task2": "queued", "task3": "queued",
                        "task4": "queued"}
    open_items = client.get(f"/users/{uid}/deliveries/open").json()
    assert {d["label"] for d in open_items} == set(by_label)  # all five are on the elder screen's list
    assert all(d["late"] for d in open_items)


def test_a_medicine_that_waited_past_its_window_is_not_spoken_but_shown_and_the_family_told(client, uid):
    box = _clock(NOW - timedelta(hours=3))
    _med(client, uid, window_min=30)
    box["now"] = NOW
    client.post("/internal/medicines/tick")
    _sweep(client, box, NOW + timedelta(minutes=31))
    d = _all(client, uid)[0]
    assert d["status"] == "shown_only"
    assert client.get(f"/users/{uid}/deliveries/next").json() is None  # never offered to a voice session
    notes = client.get(f"/users/{uid}/notifications").json()
    assert [n["kind"] for n in notes] == ["medicine_undelivered"]
    assert "Telma AM" in notes[0]["body"] and "never spoken" in notes[0]["body"]
    _sweep(client, box, NOW + timedelta(minutes=40))
    assert len(client.get(f"/users/{uid}/notifications").json()) == 1  # told once


def test_the_family_is_told_once_when_a_reminder_was_not_spoken_on_time(client, uid):
    box = _clock(NOW)
    _reminder(client, uid)
    _fire(client, box, NOW + timedelta(minutes=5, seconds=5))
    _sweep(client, box, NOW + timedelta(minutes=5, seconds=60))  # only a minute late: still fine
    assert client.get(f"/users/{uid}/notifications").json() and all(
        n["kind"] != "undelivered" for n in client.get(f"/users/{uid}/notifications").json()
    )
    _sweep(client, box, NOW + timedelta(minutes=8))
    _sweep(client, box, NOW + timedelta(minutes=9))
    undelivered = [n for n in client.get(f"/users/{uid}/notifications").json() if n["kind"] == "undelivered"]
    assert len(undelivered) == 1 and "tea" in undelivered[0]["body"] and "not spoken" in undelivered[0]["body"]


def test_an_item_that_is_no_longer_needed_is_superseded_not_spoken(client, uid):
    box = _clock(NOW)
    rid = _reminder(client, uid)
    _fire(client, box, NOW + timedelta(minutes=5, seconds=5))
    client.post(f"/users/{uid}/reminders/{rid}/complete")
    _sweep(client, box, box["now"] + timedelta(seconds=10))
    assert _all(client, uid)[0]["status"] == "superseded"
    assert client.get(f"/users/{uid}/deliveries/next").json() is None


def test_late_flag_and_open_list_exclude_finished_items(client, uid):
    box = _clock(NOW)
    d = _queued(client, uid, box)
    assert d["late"] is False
    box["now"] += timedelta(minutes=5)
    assert client.get(f"/users/{uid}/deliveries/next").json()["late"] is True
    base = f"/users/{uid}/deliveries/{d['id']}"
    client.post(f"{base}/claim", json={"session": "A"})
    client.post(f"{base}/spoken", json={"session": "A"})
    assert [x["status"] for x in client.get(f"/users/{uid}/deliveries/open").json()] == ["spoken"]
    client.post(f"{base}/ack", json={})
    assert client.get(f"/users/{uid}/deliveries/open").json() == []
    assert _all(client, uid)[0]["status"] == "acknowledged"


# ---- acknowledgement hooks ----------------------------------------------------------------------------------
def _spoken_medicine(client, uid, box):
    _med(client, uid)
    box["now"] = NOW
    client.post("/internal/medicines/tick")
    d = client.get(f"/users/{uid}/deliveries/next").json()
    client.post(f"/users/{uid}/deliveries/{d['id']}/claim", json={"session": "A"})
    client.post(f"/users/{uid}/deliveries/{d['id']}/spoken", json={"session": "A"})
    return d


def _dose_id(client, uid):
    return client.get(f"/users/{uid}/medicines/due").json()["current"][0]["id"]


def test_tapping_taken_acknowledges_the_delivery(client, uid):
    box = _clock(NOW - timedelta(hours=3))
    d = _spoken_medicine(client, uid, box)
    client.post(f"/users/{uid}/medicine-doses/{_dose_id(client, uid)}/taken")
    got = [x for x in _all(client, uid) if x["id"] == d["id"]][0]
    assert got["status"] == "acknowledged" and got["outcome"] == "taken"


def test_a_spoken_yes_to_the_pending_taken_question_acknowledges_it(client, uid):
    box = _clock(NOW - timedelta(hours=3))
    d = _spoken_medicine(client, uid, box)
    a = client.post(f"/users/{uid}/actions/propose",
                    json={"action_type": "MEDICINE_TAKEN", "payload": {"dose_id": _dose_id(client, uid)}}).json()
    assert client.post(f"/users/{uid}/actions/{a['id']}/confirm").status_code == 200
    got = [x for x in _all(client, uid) if x["id"] == d["id"]][0]
    assert (got["status"], got["outcome"]) == ("acknowledged", "taken")


def test_a_no_answer_is_recorded_as_not_taken_and_the_family_is_told_without_advice(client, uid):
    box = _clock(NOW - timedelta(hours=3))
    d = _spoken_medicine(client, uid, box)
    dose = _dose_id(client, uid)
    a = client.post(f"/users/{uid}/actions/propose",
                    json={"action_type": "MEDICINE_TAKEN", "payload": {"dose_id": dose, "asked": "delivery"}}).json()
    assert client.post(f"/users/{uid}/actions/{a['id']}/reject", params={"answer": "no"}).status_code == 200
    got = [x for x in _all(client, uid) if x["id"] == d["id"]][0]
    assert (got["status"], got["outcome"]) == ("acknowledged", "not_taken")
    history = client.get(f"/users/{uid}/medicine-doses").json()
    assert [h["status"] for h in history] == ["not_taken"]
    notes = client.get(f"/users/{uid}/notifications").json()
    assert [n["kind"] for n in notes] == ["medicine_not_taken"] and "self-reported" in notes[0]["body"]
    # no repeat nagging: the next ticks queue nothing for this dose
    box["now"] = NOW + timedelta(minutes=20)
    assert client.post("/internal/medicines/tick").json() == {"reminded": [], "unconfirmed": []}


def test_rejecting_for_any_other_reason_records_nothing_about_the_dose(client, uid):
    box = _clock(NOW - timedelta(hours=3))
    _spoken_medicine(client, uid, box)
    a = client.post(f"/users/{uid}/actions/propose",
                    json={"action_type": "MEDICINE_TAKEN", "payload": {"dose_id": _dose_id(client, uid)}}).json()
    client.post(f"/users/{uid}/actions/{a['id']}/reject")  # e.g. cleared by a safety reply
    assert client.get(f"/users/{uid}/medicine-doses").json()[0]["status"] != "not_taken"
    assert client.get(f"/users/{uid}/notifications").json() == []


def test_completing_a_reminder_acknowledges_its_delivery(client, uid):
    box = _clock(NOW)
    rid = _reminder(client, uid)
    _fire(client, box, NOW + timedelta(minutes=5, seconds=5))
    client.post(f"/users/{uid}/reminders/{rid}/complete")
    assert _all(client, uid)[0]["status"] in ("acknowledged", "superseded")


def test_the_unconfirmed_notice_says_how_many_reminders_were_really_spoken(client, uid):
    box = _clock(NOW - timedelta(hours=3))
    _med(client, uid, max_reminders=2, repeat_minutes=15)
    for step in (0, 15, 30):
        box["now"] = NOW + timedelta(minutes=step)
        client.post("/internal/medicines/tick")
    notes = [n for n in client.get(f"/users/{uid}/notifications").json() if n["kind"] == "medicine_unconfirmed"]
    assert len(notes) == 1 and "cannot tell" in notes[0]["body"]
    assert "none of the 2 reminders could be spoken" in notes[0]["body"]


def test_unknown_delivery_or_other_users_delivery_is_not_found(client, uid):
    assert client.post(f"/users/{uid}/deliveries/999/claim", json={"session": "A"}).status_code == 404
    assert client.get("/users/999/deliveries/next").status_code == 404


def test_dashboard_list_covers_every_status_for_the_requested_days(client, uid):
    box = _clock(NOW)
    _reminder(client, uid)
    _fire(client, box, NOW + timedelta(minutes=5, seconds=5))
    assert len(client.get(f"/users/{uid}/deliveries", params={"days": 1}).json()) == 1
    box["now"] = NOW + timedelta(days=3)
    assert client.get(f"/users/{uid}/deliveries", params={"days": 1}).json() == []


def test_the_race_helper_needs_a_queued_item(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'x.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(m.User(id=1, name="Demo (synthetic)"))
        s.flush()
        s.add(m.Delivery(user_id=1, kind="reminder", ref_id=1, attempt=1, due_at=NOW, status="spoken"))
        s.commit()
        assert claim_delivery(s, 1, 1, "A", NOW) is False
