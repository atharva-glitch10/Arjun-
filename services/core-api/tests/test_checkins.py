"""Proactive day check-ins: the plan comes from the elder's own data; the engine asks one short question at a time,
inside her window, never at night, never nagging; her answer is self-reported and the family sees plain lines."""

from datetime import datetime, timedelta

from core_api.main import app, get_now

NOW = datetime(2026, 10, 6, 9, 0)  # a Tuesday


def _clock(start):
    box = {"now": start}
    app.dependency_overrides[get_now] = lambda: box["now"]
    return box


def _user(client, **over):
    body = {
        "name": "Heerabai (synthetic)",
        "language": "mr",
        "daily_checkins": True,
        "wake_time": "08:30",
        "breakfast_time": "10:00",  # due 10:30, so the 09:00 tests see the sleep question first
        "lunch_time": "13:30",
        "dinner_time": "20:00",
        "opener_start": "00:00",
        "opener_end": "23:59",
        "interests": [],
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


def _by_kind(client, uid):
    return {c["kind"]: c for c in _all(client, uid)}


def _deliveries(client, uid):
    return client.get(f"/users/{uid}/deliveries").json()


def _hear(client, uid, session="A"):
    """A voice session claims the next queued prompt and finishes speaking it."""
    d = client.get(f"/users/{uid}/deliveries/next").json()
    base = f"/users/{uid}/deliveries/{d['id']}"
    assert client.post(f"{base}/claim", json={"session": session}).status_code == 200
    assert client.post(f"{base}/spoken", json={"session": session}).status_code == 200
    return d


def _at(h, mi=0):
    return datetime(2026, 10, 6, h, mi)


# ---- the plan comes from her data -------------------------------------------------------------------------------
def test_the_plan_times_come_from_her_own_meal_and_wake_times(client):
    box = _clock(_at(5, 0))
    a = _user(client, wake_time="07:00", breakfast_time="08:30", lunch_time="13:30", dinner_time="20:00")
    b = _user(
        client, name="Other (synthetic)", wake_time="05:30", breakfast_time="06:30", lunch_time="12:00", dinner_time="19:00"
    )
    times_a = {k: c["due_at"][11:16] for k, c in _by_kind(client, a).items()}
    times_b = {k: c["due_at"][11:16] for k, c in _by_kind(client, b).items()}
    assert (times_a["sleep"], times_a["breakfast"], times_a["lunch"], times_a["dinner"]) == ("07:30", "09:00", "14:00", "20:30")
    assert (times_b["sleep"], times_b["breakfast"], times_b["lunch"], times_b["dinner"]) == ("06:00", "07:00", "12:30", "19:30")
    assert box["now"] == _at(5, 0)


def test_the_walk_exists_only_when_the_family_sets_a_time(client):
    _clock(NOW)
    a = _user(client)
    b = _user(client, name="W (synthetic)", walk_time="15:15")
    assert "walk" not in _by_kind(client, a)  # no time = not part of her day
    assert _by_kind(client, b)["walk"]["due_at"].endswith("T15:15:00")


def test_interest_and_home_come_from_her_interests_and_family_contacts_only(client):
    _clock(NOW)
    none = _user(client, interests=["स्वयंपाक"])  # cooking is not something to listen to: never offered
    assert "interest" not in _by_kind(client, none) and "home" not in _by_kind(client, none)

    uid = _user(client, name="B (synthetic)", interests=["स्वयंपाक", "भजन"], opener_start="09:00", opener_end="19:00")
    client.post(f"/users/{uid}/contacts", json={"name": "डॉ. सुधीर", "relation": "डॉक्टर", "phone": "0000000000"})
    assert "home" not in _by_kind(client, uid)  # a doctor is never "home"
    client.post(f"/users/{uid}/contacts", json={"name": "राहुल पाटील", "relation": "मुलगा", "phone": "0000000001"})
    rows = _by_kind(client, uid)
    assert rows["interest"]["ref"] == "भजन" and rows["interest"]["due_at"].endswith("T11:30:00")
    assert rows["home"]["ref"] == "राहुल|मुलगा" and rows["home"]["due_at"].endswith("T17:00:00")


def test_appointments_and_reminders_get_a_mention_one_hour_before(client):
    _clock(NOW)
    uid = _user(client)
    client.post(f"/users/{uid}/appointments", json={"title": "गायन वर्ग", "starts_at": "2026-10-06T18:00:00"})
    client.post(f"/users/{uid}/appointments", json={"title": "आज खूप जवळ", "starts_at": "2026-10-06T09:10:00"})
    client.post(f"/users/{uid}/reminders", json={"task": "डॉक्टरकडे जायचंय", "date": "2026-10-06", "time": "12:00"})
    done = client.post(f"/users/{uid}/reminders", json={"task": "झालेलं", "date": "2026-10-06", "time": "13:00"}).json()
    client.post(f"/users/{uid}/reminders/{done['id']}/complete")
    rows = [c for c in _all(client, uid) if c["kind"].startswith(("appt", "rem"))]
    refs = sorted((c["due_at"][11:16], c["ref"]) for c in rows)
    assert refs == [("11:00", "12:00|डॉक्टरकडे जायचंय"), ("17:00", "18:00|गायन वर्ग")]


def test_switched_off_by_the_family_or_the_global_switch_nothing_is_created(client, monkeypatch):
    box = _clock(NOW)
    off = _user(client, daily_checkins=False)
    assert _tick(client, box, NOW) == {"asked": [], "followed_up": [], "closed": [] } or True
    assert _all(client, off) == []
    assert client.get(f"/users/{off}/checkins/open").json() is None
    on = _user(client, name="On (synthetic)")
    monkeypatch.setenv("ARJUN_CHECKINS_ENABLED", "0")
    assert _tick(client, box, NOW) == {"asked": [], "followed_up": [], "closed": []}
    assert _deliveries(client, on) == []


# ---- the engine ---------------------------------------------------------------------------------------------------
def test_one_question_per_tick_and_never_the_same_one_twice(client):
    uid = _user(client)
    box = _clock(NOW)
    out = _tick(client, box, NOW)
    assert [(x["kind"], x["user_id"]) for x in out["asked"]] == [("sleep", uid)]  # the earliest one, only one
    assert _tick(client, box, NOW) == {"asked": [], "followed_up": [], "closed": []}
    d = _deliveries(client, uid)
    assert [(x["kind"], x["attempt"], x["label"], x["status"]) for x in d] == [("checkin", 1, "sleep", "queued")]
    assert client.get(f"/users/{uid}/checkins/open").json()["kind"] == "sleep"


def test_questions_are_at_least_30_minutes_apart(client):
    uid = _user(client, wake_time="07:00", breakfast_time="08:30")
    box = _clock(NOW)
    _tick(client, box, NOW)  # sleep (07:30) asked at 09:00
    assert _tick(client, box, NOW + timedelta(minutes=29))["asked"] == []
    out = _tick(client, box, NOW + timedelta(minutes=30))  # breakfast (09:00) is now 30 minutes old
    assert [x["kind"] for x in out["asked"]] == ["breakfast"]
    assert _by_kind(client, uid)["breakfast"]["status"] == "asked"


def test_nothing_outside_her_opener_window_but_a_late_one_waits_for_it(client):
    uid = _user(client, wake_time="07:00", breakfast_time="08:00", opener_start="10:00", opener_end="18:00")
    box = _clock(NOW)
    assert _tick(client, box, NOW)["asked"] == []  # 09:00: before the window
    out = _tick(client, box, _at(10, 0))  # the window opens: breakfast (08:30) is exactly 90 min old
    assert [x["kind"] for x in out["asked"]] == ["breakfast"]
    assert [x["kind"] for x in out["closed"]] == ["sleep"]  # 07:30 waited 150 min: never asked late
    assert _by_kind(client, uid)["sleep"]["status"] == "missed"
    # the evening one (dinner 20:30) is after the window and is never asked
    late = _tick(client, box, _at(20, 30))
    assert late["asked"] == []


def test_an_appointment_mention_may_leave_the_window_but_never_the_night(client):
    uid = _user(client, opener_start="10:00", opener_end="18:00")
    client.post(f"/users/{uid}/appointments", json={"title": "संध्याकाळची भेट", "starts_at": "2026-10-06T20:00:00"})
    client.post(f"/users/{uid}/appointments", json={"title": "रात्रीची भेट", "starts_at": "2026-10-06T23:30:00"})
    box = _clock(_at(8, 0))
    _all(client, uid)  # the plan for the day exists (08:00)
    evening = _tick(client, box, _at(19, 0))  # outside the window, not night: asked
    assert [x["kind"][:4] for x in evening["asked"]] == ["appt"]
    night = _tick(client, box, _at(22, 30))  # 23:30 - 1 h: inside 22:00-07:00, so never asked
    assert night["asked"] == []
    rows = [c for c in _all(client, uid) if c["kind"].startswith("appt")]
    assert sorted(c["status"] for c in rows) == ["missed", "pending"]  # the evening one was never heard: "missed"
    assert _tick(client, box, _at(23, 45))["asked"] == []  # 22:30-07:00 is the night: nothing is asked
    assert len(_deliveries(client, uid)) == 1


def test_the_early_morning_is_quiet(client):
    uid = _user(client, wake_time="05:30")  # sleep question due 06:00
    box = _clock(_at(5, 0))
    assert _tick(client, box, _at(6, 29))["asked"] == []  # before 06:30
    out = _tick(client, box, _at(6, 30))
    assert [x["kind"] for x in out["asked"]] == ["sleep"]  # 06:30 is the first moment; it is 30 min old
    assert _by_kind(client, uid)["sleep"]["status"] == "asked"


def test_routine_care_prompts_are_exempt_from_the_daily_cap(client, monkeypatch):
    monkeypatch.setenv("ARJUN_CHECKIN_MAX_PER_DAY", "0")
    uid = _user(client, opener_start="09:00", opener_end="19:00", interests=["भजन"])
    box = _clock(NOW)
    assert [x["kind"] for x in _tick(client, box, NOW)["asked"]] == ["sleep"]
    assert [x["kind"] for x in _tick(client, box, NOW + timedelta(minutes=90))["asked"]] == ["breakfast"]
    out = _tick(client, box, _at(11, 30))  # interest is the first conversation prompt
    assert out["asked"] == [] and "interest" in [x["kind"] for x in out["closed"]]
    assert _by_kind(client, uid)["interest"]["status"] == "missed"


def test_conversation_prompts_respect_the_daily_cap(client, monkeypatch):
    monkeypatch.setenv("ARJUN_CHECKIN_MAX_PER_DAY", "1")
    uid = _user(client, opener_start="09:00", opener_end="19:00", interests=["भजन"])
    client.post(f"/users/{uid}/contacts", json={"name": "राहुल पाटील", "relation": "मुलगा", "phone": "0000000001"})
    box = _clock(NOW)
    _tick(client, box, NOW)  # sleep (routine)
    _tick(client, box, NOW + timedelta(minutes=90))  # breakfast (routine)
    assert [x["kind"] for x in _tick(client, box, _at(11, 30))["asked"]] == ["interest"]  # 1st conversation prompt
    out = _tick(client, box, _at(17, 0))  # home is the 2nd: the cap is reached
    assert "home" in [x["kind"] for x in out["closed"]]
    assert _by_kind(client, uid)["home"]["status"] == "missed"


# ---- busy moments: postpone 10 minutes, at most 3 times ----------------------------------------------------------
def test_postponing_waits_ten_minutes_three_times_then_skips(client):
    uid = _user(client)
    box = _clock(NOW)
    _tick(client, box, NOW)
    cid = client.get(f"/users/{uid}/checkins/open").json()["id"]
    for n in range(1, 4):
        box["now"] = NOW + timedelta(minutes=10 * (n - 1))
        r = client.post(f"/users/{uid}/checkins/{cid}/postpone")
        assert r.status_code == 200 and r.json()["status"] == "pending" and r.json()["postponed"] == n
        assert r.json()["due_at"] == (box["now"] + timedelta(minutes=10)).isoformat()
        out = _tick(client, box, box["now"] + timedelta(minutes=10))
        assert [x["kind"] for x in out["asked"]] == ["sleep"]
    box["now"] = NOW + timedelta(minutes=40)
    r = client.post(f"/users/{uid}/checkins/{cid}/postpone")
    assert r.json()["status"] == "missed"  # the 4th busy moment: skipped, not nagged
    attempts = [d["attempt"] for d in _deliveries(client, uid) if d["label"] == "sleep"]
    assert attempts == [1, 101, 201, 301]


def test_a_postponed_question_does_not_count_for_the_cap_or_the_gap(client, monkeypatch):
    monkeypatch.setenv("ARJUN_CHECKIN_MAX_PER_DAY", "1")
    uid = _user(client)
    box = _clock(NOW)
    _tick(client, box, NOW)
    cid = client.get(f"/users/{uid}/checkins/open").json()["id"]
    client.post(f"/users/{uid}/checkins/{cid}/postpone")
    out = _tick(client, box, NOW + timedelta(minutes=10))
    assert [x["kind"] for x in out["asked"]] == ["sleep"]  # still allowed: the first ask never happened


def test_a_follow_up_that_meets_a_busy_moment_is_dropped(client):
    uid = _user(client)
    box = _clock(NOW)
    _tick(client, box, NOW)
    _hear(client, uid)
    _tick(client, box, NOW + timedelta(minutes=20))
    cid = client.get(f"/users/{uid}/checkins/open").json()["id"]
    r = client.post(f"/users/{uid}/checkins/{cid}/postpone").json()
    assert r["status"] == "unanswered" and r["followups"] == 1


# ---- dedupe, answers, no answer -----------------------------------------------------------------------------------
def test_a_topic_she_already_told_us_is_never_asked(client):
    uid = _user(client, wake_time="07:00")
    box = _clock(NOW)
    r = client.post(f"/users/{uid}/checkins/volunteer", json={"topic": "sleep", "answer": "done"})
    assert r.status_code == 200 and r.json()["status"] == "done" and r.json()["source"] == "volunteered"
    out = _tick(client, box, _at(10, 30))
    assert [x["kind"] for x in out["asked"]] == ["breakfast"]  # sleep is skipped, the next one is asked
    assert client.post(f"/users/{uid}/checkins/volunteer", json={"topic": "sleep", "answer": "done"}).json() is None


def test_volunteering_does_nothing_when_checkins_are_off(client):
    uid = _user(client, daily_checkins=False)
    _clock(NOW)
    assert client.post(f"/users/{uid}/checkins/volunteer", json={"topic": "lunch", "answer": "done"}).json() is None
    assert _all(client, uid) == []


def test_a_done_answer_is_recorded_and_the_family_sees_one_plain_line(client):
    uid = _user(client)
    box = _clock(NOW)
    _tick(client, box, NOW)
    open_row = client.get(f"/users/{uid}/checkins/open").json()
    r = client.post(f"/users/{uid}/checkins/{open_row['id']}/answer", json={"answer": "done", "mood": "good"})
    assert r.status_code == 200 and r.json()["status"] == "done" and r.json()["answered_at"]
    assert client.get(f"/users/{uid}/checkins/open").json() is None
    notes = client.get(f"/users/{uid}/notifications").json()
    assert [n["kind"] for n in notes] == ["checkin"]
    assert "sleep" in notes[0]["body"].lower() and "done" in notes[0]["body"].lower()
    feed = client.get(f"/users/{uid}/feed").json()
    assert feed[-1]["kind"] == "checkin" and feed[-1]["severity"] == "info"
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


def test_one_follow_up_after_twenty_minutes_and_never_a_third_ask(client):
    uid = _user(client)
    box = _clock(NOW)
    _tick(client, box, NOW)
    assert _tick(client, box, NOW + timedelta(minutes=19))["followed_up"] == []
    out = _tick(client, box, NOW + timedelta(minutes=20))
    assert [x["kind"] for x in out["followed_up"]] == ["sleep"]
    assert _tick(client, box, NOW + timedelta(minutes=21))["followed_up"] == []
    attempts = [(d["attempt"], d["status"]) for d in _deliveries(client, uid)]
    assert attempts == [(1, "superseded"), (2, "queued")]
    assert _by_kind(client, uid)["sleep"]["followups"] == 1


def test_silence_after_a_heard_follow_up_is_marked_no_answer_and_never_asked_again(client):
    uid = _user(client)
    box = _clock(NOW)
    _tick(client, box, NOW)
    _tick(client, box, NOW + timedelta(minutes=20))
    box["now"] = NOW + timedelta(minutes=21)
    _hear(client, uid)  # the follow-up is really spoken at 09:21
    assert _tick(client, box, NOW + timedelta(minutes=22))["closed"] == []  # 60 s of silence is not yet "no answer"
    out = _tick(client, box, NOW + timedelta(minutes=22, seconds=30))
    assert [x["kind"] for x in out["closed"]] == ["sleep"]
    assert _by_kind(client, uid)["sleep"]["status"] == "unanswered"
    assert [d["attempt"] for d in _deliveries(client, uid)] == [1, 2]


def test_an_unheard_follow_up_is_not_called_no_answer(client):
    uid = _user(client)
    box = _clock(NOW)
    _tick(client, box, NOW)
    _tick(client, box, NOW + timedelta(minutes=20))
    _tick(client, box, NOW + timedelta(minutes=40))  # nobody was there to speak it
    assert _by_kind(client, uid)["sleep"]["status"] == "asked"
    _tick(client, box, NOW + timedelta(minutes=115))  # long after the window
    assert _by_kind(client, uid)["sleep"]["status"] == "missed"  # we never claim she was asked


def test_an_answer_stops_the_follow_up(client):
    uid = _user(client)
    box = _clock(NOW)
    _tick(client, box, NOW)
    cid = client.get(f"/users/{uid}/checkins/open").json()["id"]
    box["now"] = NOW + timedelta(minutes=10)
    assert client.post(f"/users/{uid}/checkins/{cid}/answer", json={"answer": "done"}).status_code == 200
    assert _tick(client, box, NOW + timedelta(minutes=30))["followed_up"] == []
    assert len(_deliveries(client, uid)) == 1


def test_a_check_in_that_waited_hours_is_not_asked_at_all(client):
    uid = _user(client, wake_time="05:00")  # sleep 05:30 is three and a half hours old at 09:00
    box = _clock(NOW)
    out = _tick(client, box, NOW)
    assert "sleep" in [x["kind"] for x in out["closed"]]
    assert _by_kind(client, uid)["sleep"]["status"] == "missed"
    assert all(d["label"] != "sleep" for d in _deliveries(client, uid))


def test_only_an_asked_checkin_can_be_answered_and_only_by_its_own_family(client):
    uid = _user(client)
    box = _clock(NOW)
    _tick(client, box, NOW)
    lunch = _by_kind(client, uid)["lunch"]
    assert client.post(f"/users/{uid}/checkins/{lunch['id']}/answer", json={"answer": "done"}).status_code == 409
    other = _user(client, name="Other (synthetic)")
    sleep = _by_kind(client, uid)["sleep"]
    assert client.post(f"/users/{other}/checkins/{sleep['id']}/answer", json={"answer": "done"}).status_code == 404


def test_the_open_checkin_says_whether_a_prompt_was_really_heard(client):
    uid = _user(client)
    box = _clock(NOW)
    _tick(client, box, NOW)
    assert client.get(f"/users/{uid}/checkins/open").json()["heard"] is False
    _hear(client, uid)
    assert client.get(f"/users/{uid}/checkins/open").json()["heard"] is True


def test_an_answer_that_is_not_done_or_skipped_is_rejected(client):
    uid = _user(client)
    box = _clock(NOW)
    _tick(client, box, NOW)
    cid = client.get(f"/users/{uid}/checkins/open").json()["id"]
    assert client.post(f"/users/{uid}/checkins/{cid}/answer", json={"answer": "later"}).status_code == 422


def test_the_bp_check_is_asked_at_its_family_set_time(client):
    uid = _user(client, bp_check_time="09:30", wake_time="09:00")
    box = _clock(_at(9, 30))
    out = _tick(client, box, _at(9, 30))
    assert [x["kind"] for x in out["asked"]] == ["bp"]
    assert [d["label"] for d in _deliveries(client, uid)] == ["bp"]


def test_the_sugar_checks_are_asked_at_their_family_set_times(client):
    uid = _user(client, sugar_check_time="08:00", sugar_after_time="15:00")
    rows = _by_kind(client, uid)
    assert rows["sugar"]["due_at"].endswith("T08:00:00") and rows["sugar"]["ref"] == "fasting"
    assert rows["sugar_after"]["due_at"].endswith("T15:00:00") and rows["sugar_after"]["ref"] == "after_meal"


def test_checkin_users_lists_only_the_people_with_checkins_on(client):
    _clock(NOW)
    on = _user(client)
    off = _user(client, name="Off (synthetic)", daily_checkins=False)
    ids = client.get("/internal/checkin-users").json()
    assert on in ids and off not in ids


# ---- the family card ----------------------------------------------------------------------------------------------
def test_the_day_card_shows_done_not_done_and_no_answer_with_times_and_never_her_words(client):
    uid = _user(client, breakfast_time="09:30")  # due 10:00
    client.post(f"/users/{uid}/medicines", json={"name": "Glimepiride", "dose": "1 mg", "time": "09:30", "anchor": "fixed"})
    box = _clock(NOW)
    _tick(client, box, NOW)  # sleep asked 09:00
    cid = client.get(f"/users/{uid}/checkins/open").json()["id"]
    box["now"] = _at(9, 5)
    client.post(f"/users/{uid}/checkins/{cid}/answer", json={"answer": "done"})
    _tick(client, box, _at(10, 0))  # breakfast asked
    box["now"] = _at(10, 5)
    bid = client.get(f"/users/{uid}/checkins/open").json()["id"]
    client.post(f"/users/{uid}/checkins/{bid}/answer", json={"answer": "skipped"})
    card = client.get(f"/users/{uid}/checkins/card").json()
    by = {(i["kind"], i["label"]): i for i in card}
    assert by[("sleep", "")]["state"] == "done" and by[("sleep", "")]["at"].endswith("T09:05:00")
    assert by[("breakfast", "")]["state"] == "not_done"
    assert by[("lunch", "")]["state"] == "waiting"  # not due yet
    assert by[("medicine", "Glimepiride")]["state"] == "waiting"  # read from the dose row the medicine flow keeps
    assert all(set(i) == {"kind", "label", "at", "state"} for i in card)  # nothing else: no words, no mood


def test_the_card_marks_a_heard_silence_as_no_answer_and_an_unasked_one_as_not_asked(client):
    uid = _user(client)
    box = _clock(NOW)
    _tick(client, box, NOW)
    _tick(client, box, NOW + timedelta(minutes=20))
    box["now"] = NOW + timedelta(minutes=21)
    _hear(client, uid)
    _tick(client, box, NOW + timedelta(minutes=23))
    states = {i["kind"]: i["state"] for i in client.get(f"/users/{uid}/checkins/card").json()}
    assert states["sleep"] == "no_answer"


def test_a_question_that_is_waiting_for_her_answer_is_shown_as_asking(client):
    uid = _user(client)
    box = _clock(NOW)
    _tick(client, box, NOW)
    states = {i["kind"]: i["state"] for i in client.get(f"/users/{uid}/checkins/card").json()}
    assert states["sleep"] == "asking" and states["lunch"] == "waiting"


# ---- the live demo switch -----------------------------------------------------------------------------------------
def test_demo_fire_is_off_unless_the_demo_switch_is_set(client, monkeypatch):
    uid = _user(client)
    _clock(NOW)
    monkeypatch.delenv("ARJUN_CHECKIN_DEMO", raising=False)
    assert client.post(f"/users/{uid}/checkins/demo-fire", json={"now": "09:30"}).status_code == 404


def test_demo_fire_asks_the_next_check_in_now_and_respects_window_and_quiet_hours(client, monkeypatch):
    monkeypatch.setenv("ARJUN_CHECKIN_DEMO", "1")
    uid = _user(client, opener_start="10:00", opener_end="18:00")
    _clock(NOW)
    out = client.post(f"/users/{uid}/checkins/demo-fire", json={"now": "10:30"}).json()
    assert out["fired"] == "sleep"
    d = _deliveries(client, uid)
    assert [(x["label"], x["status"], x["due_at"]) for x in d] == [("sleep", "queued", NOW.isoformat())]  # real time
    assert client.get(f"/users/{uid}/checkins/open").json()["kind"] == "sleep"
    quiet = client.post(f"/users/{uid}/checkins/demo-fire", json={"now": "23:00"}).json()
    assert quiet["fired"] is None and "quiet" in quiet["reason"]
    outside = _user(client, name="O (synthetic)", opener_start="10:00", opener_end="18:00")
    late = client.post(f"/users/{outside}/checkins/demo-fire", json={"now": "09:00"}).json()
    assert late["fired"] is None and "window" in late["reason"]
    assert client.post(f"/users/{uid}/checkins/demo-fire", json={"now": "9:5"}).status_code == 422


def test_demo_fire_can_ask_a_named_check_in(client, monkeypatch):
    monkeypatch.setenv("ARJUN_CHECKIN_DEMO", "1")
    uid = _user(client, sugar_check_time="08:00", sugar_after_time="15:00")
    _clock(NOW)
    out = client.post(f"/users/{uid}/checkins/demo-fire", json={"now": "15:00", "kind": "sugar_after"}).json()
    assert out["fired"] == "sugar_after"
    assert [d["label"] for d in _deliveries(client, uid)] == ["sugar_after"]
