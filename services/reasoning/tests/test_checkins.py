"""Proactive day check-ins on the reasoning side: a queued check-in is spoken from a fixed template filled only from
SQL; her answer is accepted only when core-api says the prompt was really heard, is read by rules (then one short
LLM JSON reading), and is answered in ONE short line. Busy moments postpone a question; safety always wins.

No advice, no score: "done" / "skipped" is stored as self-reported.
"""

from datetime import datetime

import pytest
from reasoning_svc import replies as rp
from reasoning_svc.core_client import CoreClient
from reasoning_svc.turn import TurnEngine

NOW = datetime(2026, 10, 6, 9, 0)
MR = rp.R["mr"]
VOLUNTEERABLE = ("sleep", "breakfast", "lunch", "walk", "dinner", "home")


class Clock:
    """A hand-set monotonic clock, so 'she spoke 2 minutes ago' is testable."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def set_core_now(value):
    from core_api.main import app, get_now

    app.dependency_overrides[get_now] = lambda: value


def at(h, mi=0):
    return datetime(2026, 10, 6, h, mi)


def make_engine(core_http, *, clock_at=NOW, evon=None, ask_first=True):
    mono = Clock()
    eng = TurnEngine(CoreClient(core_http), evon=evon, clock=lambda: clock_at, mono=mono, ask_first=ask_first)
    eng.mono = mono  # type: ignore[attr-defined]
    return eng


def setup_user(core_http, uid, **over):
    body = {
        "daily_checkins": True,
        "wake_time": "07:00",
        "lunch_time": "13:00",
        "dinner_time": "20:00",
        "opener_start": "07:00",
        "opener_end": "21:00",
        "interests": ["भजन", "स्वयंपाक"],
    }
    body.update(over)
    r = core_http.patch(f"/users/{uid}", json=body)
    assert r.status_code == 200, r.text
    return uid


def add_family(core_http, uid):
    core_http.post(f"/users/{uid}/contacts", json={"name": "राहुल", "relation": "मुलगा", "phone": "0000000001"})


def tick(core_http, when=NOW):
    set_core_now(when)
    r = core_http.post("/internal/checkins/tick")
    assert r.status_code == 200, r.text
    return r.json()


def rows(core_http, uid):
    return {c["kind"]: c for c in core_http.get(f"/users/{uid}/checkins").json()}


def ask(core_http, uid, kind):
    """Tick at the moment `kind` is due (marking sleep told, so it is not asked first). Returns the due time."""
    set_core_now(at(6, 0))
    due = datetime.fromisoformat(rows(core_http, uid)[kind]["due_at"])
    set_core_now(due)
    for other, row in rows(core_http, uid).items():  # whatever was due earlier has been told already
        if other != kind and datetime.fromisoformat(row["due_at"]) < due and other in VOLUNTEERABLE:
            core_http.post(f"/users/{uid}/checkins/volunteer", json={"topic": other, "answer": "done"})
    out = tick(core_http, due)
    assert [x["kind"] for x in out["asked"] if x["user_id"] == uid] == [kind], out
    return due


def hear(engine, uid, session="s1"):
    engine.mono.t += 200  # she has been quiet for a while: the question is not postponed
    item = engine.deliver_next(uid, session)
    assert item is not None and item["kind"] == "checkin", item
    engine.deliver_spoken(uid, item["delivery_id"], session)
    return item


def open_checkin(core_http, uid):
    return core_http.get(f"/users/{uid}/checkins/open").json()


# ---- the prompts: fixed wording, filled only from her data ------------------------------------------------------
def test_the_sleep_prompt_greets_her_by_name_from_sql(core_http, uid):
    setup_user(core_http, uid)
    eng = make_engine(core_http)
    ask(core_http, uid, "sleep")
    item = eng.deliver_next(uid, "s1")
    assert item["screen"] == "reply" and item["awaiting_confirmation"] is False
    assert item["text"] == "नमस्कार Aaji, रात्री झोप नीट लागली का?"  # "(synthetic)" is never spoken


def test_the_honorific_is_used_when_the_family_set_one(core_http, uid):
    setup_user(core_http, uid, honorific="आजी")
    ask(core_http, uid, "sleep")
    assert make_engine(core_http).deliver_next(uid, "s1")["text"] == "नमस्कार आजी, रात्री झोप नीट लागली का?"


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("breakfast", "नाश्ता झाला का?"),
        ("lunch", "दुपारचं जेवण झालं का? काय केलं होतं?"),
        ("walk", "आज थोडं फिरणं झालं का?"),
        ("dinner", "रात्रीचं जेवण झालं का? आजचा दिवस कसा गेला?"),
    ],
)
def test_the_meal_and_walk_prompts_are_the_fixed_lines(core_http, uid, kind, expected):
    setup_user(core_http, uid)
    ask(core_http, uid, kind)
    item = make_engine(core_http).deliver_next(uid, "s1")
    assert item["kind"] == "checkin" and item["text"] == expected


def test_the_interest_prompt_comes_from_her_interests(core_http, uid):
    setup_user(core_http, uid)
    ask(core_http, uid, "interest")
    assert make_engine(core_http).deliver_next(uid, "s1")["text"] == "आज भजन ऐकायचं आहे का?"


def test_the_home_prompt_comes_from_her_family_contacts(core_http, uid):
    setup_user(core_http, uid)
    add_family(core_http, uid)
    ask(core_http, uid, "home")
    assert make_engine(core_http).deliver_next(uid, "s1")["text"] == "आज राहुलशी बोलणं झालं का?"


def test_a_different_user_gets_different_names_and_times(core_http, uid):
    setup_user(core_http, uid, interests=["अभंग"])
    r = core_http.post(
        "/users",
        json={"name": "Kaki (synthetic)", "language": "mr", "honorific": "काकू", "daily_checkins": True,
              "wake_time": "07:30", "interests": ["गाणी"], "opener_start": "05:00", "opener_end": "20:00"},
    )
    other = r.json()["id"]
    a, b = rows(core_http, uid), rows(core_http, other)
    assert a["sleep"]["due_at"][11:16] == "07:30" and b["sleep"]["due_at"][11:16] == "08:00"
    assert a["interest"]["ref"] == "अभंग" and b["interest"]["ref"] == "गाणी"
    ask(core_http, other, "sleep")
    assert make_engine(core_http).deliver_next(other, "s1")["text"] == "नमस्कार काकू, रात्री झोप नीट लागली का?"


def test_an_appointment_prompt_names_the_time_and_task_from_sql(core_http, uid):
    setup_user(core_http, uid)
    set_core_now(at(8, 0))
    core_http.post(f"/users/{uid}/appointments", json={"title": "गायन वर्ग", "starts_at": "2026-10-06T18:00"})
    appt = next(k for k in rows(core_http, uid) if k.startswith("appt"))
    ask(core_http, uid, appt)
    item = make_engine(core_http).deliver_next(uid, "s1")
    assert item["text"] == f"आज {rp.say_time('18:00', 'mr')} गायन वर्ग आहे, लक्षात आहे ना?"


# ---- her answers: done / skipped, one short line -----------------------------------------------------------------
def test_done_is_accepted_only_after_the_prompt_was_really_heard(core_http, uid):
    setup_user(core_http, uid)
    eng = make_engine(core_http)
    ask(core_http, uid, "breakfast")
    eng.handle(uid, "झालं")  # queued, never spoken: not an answer
    assert open_checkin(core_http, uid)["status"] == "asked"
    hear(eng, uid)
    res = eng.handle(uid, "झालं")
    assert res.intent == "CHECKIN_DONE" and res.reply == "छान!"
    assert open_checkin(core_http, uid) is None
    assert rows(core_http, uid)["breakfast"]["status"] == "done"
    assert core_http.get(f"/users/{uid}/deliveries").json()[0]["status"] == "acknowledged"


def test_a_skipped_meal_gets_one_short_nudge_and_no_advice(core_http, uid):
    setup_user(core_http, uid)
    eng = make_engine(core_http)
    ask(core_http, uid, "lunch")
    hear(eng, uid)
    res = eng.handle(uid, "नाही, खाल्लं नाही")
    assert res.intent == "CHECKIN_SKIPPED" and res.reply == MR["checkin_skipped_lunch"]
    assert res.reply.count("।") + res.reply.count(".") <= 2  # one short sentence plus the acknowledgement
    assert not any(w in res.reply for w in ("डॉक्टर", "औषध", "आरोग्य", "वाटतं"))
    assert rows(core_http, uid)["lunch"]["status"] == "skipped"


def test_sleep_walk_and_appointment_answers_have_their_own_lines(core_http, uid):
    setup_user(core_http, uid)
    eng = make_engine(core_http)
    ask(core_http, uid, "sleep")
    hear(eng, uid)
    assert eng.handle(uid, "हो, छान झोप लागली").reply == MR["checkin_done_sleep"]
    ask(core_http, uid, "walk")
    hear(eng, uid)
    res = eng.handle(uid, "आज नाही गेले")
    assert res.reply == MR["checkin_skipped_walk"] == "ठीक आहे."  # a walk gets no nudge


def test_a_sleep_answer_of_no_is_read_as_not_done(core_http, uid):
    setup_user(core_http, uid)
    eng = make_engine(core_http)
    ask(core_http, uid, "sleep")
    hear(eng, uid)
    assert eng.handle(uid, "झोप नीट लागली नाही").intent == "CHECKIN_SKIPPED"


def test_appointment_yes_and_no_answers(core_http, uid):
    setup_user(core_http, uid)
    set_core_now(at(8, 0))
    core_http.post(f"/users/{uid}/appointments", json={"title": "गायन वर्ग", "starts_at": "2026-10-06T18:00"})
    eng = make_engine(core_http)
    appt = next(k for k in rows(core_http, uid) if k.startswith("appt"))
    ask(core_http, uid, appt)
    hear(eng, uid)
    res = eng.handle(uid, "विसरले होते")
    assert res.intent == "CHECKIN_SKIPPED"
    assert res.reply == f"ठीक आहे. आज {rp.say_time('18:00', 'mr')} गायन वर्ग आहे."


def test_a_pending_question_is_never_replaced_by_a_check_in_answer(core_http, uid):
    setup_user(core_http, uid)
    eng = make_engine(core_http)
    ask(core_http, uid, "breakfast")
    hear(eng, uid)
    eng.handle(uid, "उद्या सकाळी दहा वाजता डॉक्टरकडे जायचं आहे आठवण कर मला")
    assert core_http.get(f"/users/{uid}/actions/pending").json() is not None
    res = eng.handle(uid, "हो")
    assert res.intent != "CHECKIN_DONE"
    assert open_checkin(core_http, uid)["status"] == "asked"


def test_a_medicine_answer_is_the_medicine_not_a_check_in(core_http, uid):
    setup_user(core_http, uid)
    set_core_now(at(8, 0))
    core_http.post(f"/users/{uid}/medicines", json={"name": "Telma AM", "dose": "40 mg", "time": "08:50", "anchor": "fixed"})
    eng = make_engine(core_http)
    ask(core_http, uid, "breakfast")
    hear(eng, uid)
    set_core_now(at(9, 0))
    core_http.post("/internal/medicines/tick")
    med = eng.deliver_next(uid, "s2")
    assert med is not None and med["kind"] == "medicine"
    eng.deliver_spoken(uid, med["delivery_id"], "s2")
    res = eng.handle(uid, "हो")  # "yes" right after a medicine prompt belongs to the medicine
    assert res.intent != "CHECKIN_DONE"
    assert open_checkin(core_http, uid)["status"] == "asked"


# ---- the LLM reading: strict JSON, only when the rules cannot tell ----------------------------------------------
class FakeLLM:
    def __init__(self, data):
        self.data, self.calls = data, []

    def extract_intent(self, *args, **kwargs):
        return None

    def companion_reply(self, *args, **kwargs):
        return None

    def media_understanding(self, *args, **kwargs):
        return None

    def checkin_understanding(self, topic, text, timeout=None):
        self.calls.append((topic, text))
        return self.data


def test_the_llm_reads_an_answer_the_rules_cannot_and_the_rules_win_first(core_http, uid):
    setup_user(core_http, uid)
    llm = FakeLLM({"topic": "lunch", "status": "done", "note": "ate dal rice"})
    eng = make_engine(core_http, evon=llm)
    ask(core_http, uid, "lunch")
    hear(eng, uid)
    assert eng.handle(uid, "वरण भात आणि भाजी").intent == "CHECKIN_DONE"
    assert llm.calls == [("lunch", "वरण भात आणि भाजी")]
    ask(core_http, uid, "dinner")
    hear(eng, uid)
    eng.handle(uid, "झालं")
    assert len(llm.calls) == 1  # the clear word never reached the LLM


@pytest.mark.parametrize(
    "data",
    [{"topic": "lunch", "status": "unclear", "note": ""}, {"topic": "walk", "status": "done", "note": ""},
     {"topic": "lunch", "status": "maybe"}, None],
)
def test_unclear_wrong_topic_or_broken_llm_output_is_not_an_answer(core_http, uid, data):
    setup_user(core_http, uid)
    eng = make_engine(core_http, evon=FakeLLM(data))
    ask(core_http, uid, "lunch")
    hear(eng, uid)
    assert eng.handle(uid, "आज हवा छान आहे").intent != "CHECKIN_DONE"
    assert open_checkin(core_http, uid)["status"] == "asked"


# ---- safety wins ------------------------------------------------------------------------------------------------
def test_a_health_complaint_in_the_answer_goes_to_the_symptom_flow_not_the_check_in(core_http, uid):
    setup_user(core_http, uid)
    eng = make_engine(core_http)
    ask(core_http, uid, "breakfast")
    hear(eng, uid)
    res = eng.handle(uid, "नाही, पोट दुखतंय")
    assert res.intent not in ("CHECKIN_DONE", "CHECKIN_SKIPPED")
    assert open_checkin(core_http, uid)["status"] == "asked"  # not recorded as "skipped"


def test_an_emergency_in_the_answer_is_the_fixed_safety_reply(core_http, uid):
    setup_user(core_http, uid)
    eng = make_engine(core_http)
    ask(core_http, uid, "walk")
    hear(eng, uid)
    res = eng.handle(uid, "छातीत दुखतंय, श्वास घेता येत नाही")
    assert res.mode == "safety" and "112" in res.reply
    assert open_checkin(core_http, uid)["status"] == "asked"


def test_loneliness_in_the_answer_is_not_a_check_in_answer(core_http, uid):
    setup_user(core_http, uid)
    add_family(core_http, uid)
    eng = make_engine(core_http)
    ask(core_http, uid, "home")
    hear(eng, uid)
    res = eng.handle(uid, "नाही, मला खूप एकटं वाटतं")
    assert res.intent not in ("CHECKIN_DONE", "CHECKIN_SKIPPED")


# ---- busy moments ----------------------------------------------------------------------------------------------
def test_media_playing_postpones_the_question_ten_minutes(core_http, uid):
    setup_user(core_http, uid)
    eng = make_engine(core_http)
    ask(core_http, uid, "breakfast")
    assert eng.deliver_next(uid, "s1", media_playing=True) is None
    row = rows(core_http, uid)["breakfast"]
    assert row["status"] == "pending" and row["postponed"] == 1
    assert datetime.fromisoformat(row["due_at"]) == datetime(2026, 10, 6, 8, 40)  # 8:30 + 10 minutes
    assert core_http.get(f"/users/{uid}/deliveries").json()[0]["status"] == "superseded"
    # ten minutes later, nothing playing: it is asked and spoken
    out = tick(core_http, datetime.fromisoformat(row["due_at"]))
    assert [x["kind"] for x in out["asked"]] == ["breakfast"]
    assert eng.deliver_next(uid, "s1")["text"] == "नाश्ता झाला का?"


def test_a_conversation_in_the_last_two_minutes_postpones_the_question(core_http, uid):
    setup_user(core_http, uid)
    eng = make_engine(core_http)
    ask(core_http, uid, "breakfast")
    eng.handle(uid, "आज हवामान कसं आहे")
    eng.mono.t += 60  # type: ignore[attr-defined]
    assert eng.deliver_next(uid, "s1") is None
    assert rows(core_http, uid)["breakfast"]["postponed"] == 1
    eng.mono.t += 130  # type: ignore[attr-defined]
    tick(core_http, datetime.fromisoformat(rows(core_http, uid)["breakfast"]["due_at"]))
    assert eng.deliver_next(uid, "s1") is not None


def test_a_fresh_safety_reply_postpones_the_question(core_http, uid):
    setup_user(core_http, uid)
    eng = make_engine(core_http)
    ask(core_http, uid, "breakfast")
    eng.handle(uid, "छातीत दुखतंय")
    eng.mono.t += 119  # type: ignore[attr-defined]
    assert eng.deliver_next(uid, "s1") is None
    assert rows(core_http, uid)["breakfast"]["postponed"] == 1


def test_a_reminder_being_spoken_postpones_the_question(core_http, uid):
    setup_user(core_http, uid)
    eng = make_engine(core_http)
    set_core_now(at(8, 0))
    core_http.post(f"/users/{uid}/reminders", json={"task": "औषध", "date": "2026-10-06", "time": "08:20"})
    due = ask(core_http, uid, "breakfast")
    set_core_now(due)
    core_http.post("/internal/reminders/fire-due")
    rem = core_http.get(f"/users/{uid}/deliveries/next").json()
    if rem["kind"] != "reminder":  # the older queued item first: claim the reminder itself
        rem = next(d for d in core_http.get(f"/users/{uid}/deliveries").json() if d["kind"] == "reminder")
    core_http.post(f"/users/{uid}/deliveries/{rem['id']}/claim", json={"session": "other"})
    assert eng.deliver_next(uid, "s1") is None
    assert rows(core_http, uid)["breakfast"]["postponed"] == 1


def test_after_three_postponements_the_question_is_skipped(core_http, uid):
    setup_user(core_http, uid)
    eng = make_engine(core_http)
    ask(core_http, uid, "breakfast")
    for n in range(3):
        assert eng.deliver_next(uid, "s1", media_playing=True) is None
        row = rows(core_http, uid)["breakfast"]
        assert row["postponed"] == n + 1
        tick(core_http, datetime.fromisoformat(row["due_at"]))
    assert eng.deliver_next(uid, "s1", media_playing=True) is None
    assert rows(core_http, uid)["breakfast"]["status"] == "missed"
    assert eng.deliver_next(uid, "s1") is None


def test_a_reminder_or_medicine_is_never_postponed_by_the_check_in_rule(core_http, uid):
    setup_user(core_http, uid)
    set_core_now(at(8, 0))
    core_http.post(f"/users/{uid}/reminders", json={"task": "चहा", "date": "2026-10-06", "time": "08:30"})
    set_core_now(at(8, 30))
    core_http.post("/internal/reminders/fire-due")
    eng = make_engine(core_http)
    item = eng.deliver_next(uid, "s1", media_playing=True)  # media is playing, but a reminder is not a check-in
    assert item is not None and item["kind"] == "reminder"


# ---- she told us first ------------------------------------------------------------------------------------------
def test_a_meal_she_mentions_on_her_own_is_not_asked(core_http, uid):
    setup_user(core_http, uid)
    eng = make_engine(core_http, clock_at=at(8, 40))
    set_core_now(at(6, 0))
    rows(core_http, uid)
    eng.handle(uid, "मी नाश्ता केला")
    row = rows(core_http, uid)["breakfast"]
    assert row["status"] == "done" and row["source"] == "volunteered"
    out = tick(core_http, at(8, 40))
    assert "breakfast" not in [x["kind"] for x in out["asked"]]


def test_a_plain_jevle_is_lunch_in_the_afternoon_and_not_guessed_in_the_morning(core_http, uid):
    setup_user(core_http, uid)
    set_core_now(at(6, 0))
    rows(core_http, uid)
    morning = make_engine(core_http, clock_at=at(9, 0))
    morning.handle(uid, "मी जेवले")
    assert rows(core_http, uid)["lunch"]["status"] == "pending" and rows(core_http, uid)["dinner"]["status"] == "pending"
    noon = make_engine(core_http, clock_at=at(13, 10))
    noon.handle(uid, "मी जेवले")
    assert rows(core_http, uid)["lunch"]["status"] == "done"


# ---- yes to the interest -> the existing media flow; no at home -> offer the family a message -------------------
def test_yes_to_the_interest_hands_over_to_the_media_flow(core_http, uid):
    setup_user(core_http, uid)
    eng = make_engine(core_http)
    ask(core_http, uid, "interest")
    hear(eng, uid)
    res = eng.handle(uid, "हो")
    assert res.intent not in ("CHECKIN_DONE", "CHECKIN_SKIPPED")
    assert res.action.get("type") not in (None, "none") or res.intent.startswith("OPEN") or res.screen != "reply"
    assert rows(core_http, uid)["interest"]["status"] == "done"


def test_no_to_the_interest_is_one_ok(core_http, uid):
    setup_user(core_http, uid)
    eng = make_engine(core_http)
    ask(core_http, uid, "interest")
    hear(eng, uid)
    assert eng.handle(uid, "नको").reply == "ठीक आहे."


def test_not_spoken_to_family_offers_a_message_and_yes_sends_it_with_undo(core_http, uid):
    setup_user(core_http, uid)
    add_family(core_http, uid)
    eng = make_engine(core_http, ask_first=False)
    ask(core_http, uid, "home")
    hear(eng, uid)
    res = eng.handle(uid, "नाही अजून")
    assert res.reply == "त्याला निरोप पाठवू का?"
    sent = eng.handle(uid, "हो")
    assert sent.intent == "REQUEST_CAREGIVER" and "निरोप पाठवला" in sent.reply
    reqs = core_http.get(f"/users/{uid}/caregiver-requests").json()
    assert len(reqs) == 1 and "राहुल" in reqs[0]["message"]
    undone = eng.handle(uid, "नको")  # the usual undo window
    assert "रद्द" in undone.reply or "परत" in undone.reply or undone.intent == "CONFIRM_NO"


def test_declining_the_offer_sends_nothing(core_http, uid):
    setup_user(core_http, uid)
    add_family(core_http, uid)
    eng = make_engine(core_http, ask_first=False)
    ask(core_http, uid, "home")
    hear(eng, uid)
    eng.handle(uid, "नाही")
    assert eng.handle(uid, "नको").reply == "ठीक आहे."
    assert core_http.get(f"/users/{uid}/caregiver-requests").json() == []


def test_the_offer_expires_after_two_minutes(core_http, uid):
    setup_user(core_http, uid)
    add_family(core_http, uid)
    eng = make_engine(core_http, ask_first=False)
    ask(core_http, uid, "home")
    hear(eng, uid)
    eng.handle(uid, "नाही")
    eng.mono.t += 200  # type: ignore[attr-defined]
    eng.handle(uid, "हो")
    assert core_http.get(f"/users/{uid}/caregiver-requests").json() == []


def test_the_pronoun_follows_the_relation_and_never_guesses(core_http, uid):
    assert rp.pronoun_for("मुलगा", "mr") == "त्याला"
    assert rp.pronoun_for("नात", "mr") == "तिला"
    assert rp.pronoun_for("family", "mr") == "त्यांना"
    assert rp.pronoun_for("मुलगा", "en") == "him"


# ---- the follow-up ----------------------------------------------------------------------------------------------
def test_the_second_delivery_is_the_one_gentle_repeat(core_http, uid):
    setup_user(core_http, uid)
    eng = make_engine(core_http)
    ask(core_http, uid, "breakfast")
    first = eng.deliver_next(uid, "s1")
    assert first is not None
    eng.deliver_release(uid, first["delivery_id"], "s1", "interrupted")
    tick(core_http, datetime(2026, 10, 6, 8, 50))
    second = eng.deliver_next(uid, "s1")
    assert second is not None and second["delivery_id"] != first["delivery_id"]
    assert MR["checkin_again"].format(prompt="नाश्ता झाला का?") == second["text"]
    assert [d["attempt"] for d in core_http.get(f"/users/{uid}/deliveries").json()] == [1, 2]
