"""Meal check-ins on the reasoning side: a queued check-in is spoken from a fixed template, and the
elder's answer is only accepted when core-api says the prompt was really heard.

No advice, no score: "done" / "skipped" is read back in one fixed line and stored as self-reported.
"""

from datetime import datetime, timedelta

from reasoning_svc import replies as rp

NOW = datetime(2026, 10, 6, 9, 0)
MR = rp.R["mr"]


def set_core_now(value):
    from core_api.main import app, get_now

    app.dependency_overrides[get_now] = lambda: value


def make_checkin_user(core_http, uid, **over):
    body = {
        "daily_checkins": True,
        "breakfast_time": "08:00",
        "lunch_time": "13:00",
        "snack_time": "17:00",
    }
    body.update(over)
    r = core_http.patch(f"/users/{uid}", json=body)
    assert r.status_code == 200, r.text
    return uid


def tick(core_http, at=NOW):
    set_core_now(at)
    r = core_http.post("/internal/checkins/tick")
    assert r.status_code == 200, r.text
    return r.json()


def spoken_prompt(core_http, engine, uid, session="s1"):
    item = engine.deliver_next(uid, session)
    assert item is not None and item["kind"] == "checkin", item
    engine.deliver_spoken(uid, item["delivery_id"], session)
    return item


def open_checkin(core_http, uid):
    return core_http.get(f"/users/{uid}/checkins/open").json()


def checkins(core_http, uid):
    return core_http.get(f"/users/{uid}/checkins").json()


def test_a_due_meal_is_spoken_with_its_fixed_prompt(core_http, uid, engine):
    make_checkin_user(core_http, uid)
    tick(core_http)
    item = engine.deliver_next(uid, "s1")
    assert item["kind"] == "checkin" and item["screen"] == "reply"
    assert item["awaiting_confirmation"] is False
    assert item["text"] == MR["checkin_prompt_breakfast"]


def test_the_daily_walk_has_its_own_fixed_prompt_and_answer(core_http, uid, engine):
    make_checkin_user(core_http, uid, walk_time="07:30", breakfast_time="10:00")
    tick(core_http, NOW.replace(hour=7, minute=30))
    item = engine.deliver_next(uid, "s1")
    assert item["kind"] == "checkin" and item["text"] == MR["checkin_prompt_walk"]
    engine.deliver_spoken(uid, item["delivery_id"], "s1")

    res = engine.handle(uid, "हो, फिरायला गेले")
    assert res.intent == "CHECKIN_DONE" and res.reply == MR["checkin_done_walk"]
    assert checkins(core_http, uid)[0]["status"] == "done"


def test_the_snack_prompt_also_mentions_a_class_that_evening(core_http, uid, engine):
    make_checkin_user(core_http, uid, breakfast_time="10:00", snack_time="08:00")
    set_core_now(NOW - timedelta(hours=3))
    r = core_http.post(
        f"/users/{uid}/appointments",
        json={"title": "गायन वर्ग", "starts_at": "2026-10-06T18:00", "location": "गायन वर्ग"},
    )
    assert r.status_code == 201, r.text
    set_core_now(NOW)
    tick(core_http)
    item = engine.deliver_next(uid, "s1")
    assert item["kind"] == "checkin"
    assert item["text"].startswith(MR["checkin_prompt_snack"])
    assert "गायन वर्ग" in item["text"] and rp.say_time("18:00", "mr") in item["text"]


def test_done_is_accepted_only_after_the_prompt_was_really_heard(core_http, uid, engine):
    make_checkin_user(core_http, uid)
    tick(core_http)
    # queued is not heard: the same words must not silently answer the check-in
    engine.handle(uid, "झालं")
    assert open_checkin(core_http, uid)["status"] == "asked"

    spoken_prompt(core_http, engine, uid)
    res = engine.handle(uid, "झालं")
    assert res.intent == "CHECKIN_DONE"
    assert "नोंदवलं" in res.reply
    assert open_checkin(core_http, uid) is None
    row = checkins(core_http, uid)[0]
    assert (row["kind"], row["status"]) == ("breakfast", "done") and row["answered_at"]
    assert core_http.get(f"/users/{uid}/notifications").json()[0]["kind"] == "checkin"
    assert core_http.get(f"/users/{uid}/deliveries").json()[0]["status"] == "acknowledged"


def test_a_clear_no_is_recorded_as_skipped_without_advice(core_http, uid, engine):
    make_checkin_user(core_http, uid)
    tick(core_http)
    spoken_prompt(core_http, engine, uid)
    res = engine.handle(uid, "नाही, केलं नाही")
    assert res.intent == "CHECKIN_SKIPPED"
    assert "नोंदवलं" in res.reply
    assert not any(word in res.reply for word in ("प्या", "घ्या", "डॉक्टर", "आरोग्य"))
    assert checkins(core_http, uid)[0]["status"] == "skipped"


def test_a_pending_question_is_never_replaced_by_a_check_in_answer(core_http, uid, engine):
    make_checkin_user(core_http, uid)
    tick(core_http)
    spoken_prompt(core_http, engine, uid)
    engine.handle(uid, "उद्या सकाळी दहा वाजता डॉक्टरकडे जायचं आहे आठवण कर मला")
    pending = core_http.get(f"/users/{uid}/actions/pending").json()
    assert pending is not None
    res = engine.handle(uid, "हो")
    assert res.intent != "CHECKIN_DONE"
    assert open_checkin(core_http, uid)["status"] == "asked"


def test_the_second_delivery_is_the_one_follow_up(core_http, uid, engine):
    make_checkin_user(core_http, uid, breakfast_time="09:00")
    tick(core_http)
    first = engine.deliver_next(uid, "s1")
    assert first is not None
    tick(core_http, NOW + timedelta(minutes=30))
    second = engine.deliver_next(uid, "s1")
    assert second is not None and second["delivery_id"] != first["delivery_id"]
    assert MR["checkin_prompt_breakfast"] in second["text"]
    assert [d["attempt"] for d in core_http.get(f"/users/{uid}/deliveries").json()] == [1, 2]
    tick(core_http, NOW + timedelta(minutes=31))
    assert engine.deliver_next(uid, "s1") is None
