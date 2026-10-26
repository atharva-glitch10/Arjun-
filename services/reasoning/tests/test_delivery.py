"""T8 step 2: rendering a queued delivery as Arjun's spoken line, and answering the medicine question.

Boundaries: 6 (name, dose and time are read from SQL through a FIXED template, never by an LLM; no advice on missed
or skipped doses), 1 (the LLM never touches anything; reasoning proposes, core-api validates), 8 (a safety reply
is never talked over), 14 (nothing here marks anything spoken: that is the voice session's job after playback).
"""

from datetime import datetime, timedelta

import httpx
import pytest
from reasoning_svc import replies as rp
from reasoning_svc.core_client import CoreClient
from reasoning_svc.evon import EvonClient, load_intent_schema
from reasoning_svc.turn import TurnEngine

NOW = datetime(2026, 10, 6, 9, 0)
MR = rp.R["mr"]
DOSE = "१ गोळी (४० mg)"  # as the family typed it: must come back byte for byte


class Clock:
    def __init__(self, start=NOW):
        self.now = start

    def __call__(self):
        return self.now


def set_core_now(core_http, value):
    from core_api.main import app, get_now

    app.dependency_overrides[get_now] = lambda: value


def add_medicine(core_http, uid, time="09:00", **over):
    body = {"name": "टेल्मा सकाळ", "dose": DOSE, "anchor": "fixed", "time": time}
    body.update(over)
    set_core_now(core_http, NOW - timedelta(hours=3))
    r = core_http.post(f"/users/{uid}/medicines", json=body)
    assert r.status_code in (200, 201), r.text
    set_core_now(core_http, NOW)
    return r.json()["id"]


def tick(core_http, at=NOW):
    set_core_now(core_http, at)
    core_http.post("/internal/medicines/tick")
    core_http.post("/internal/reminders/fire-due")


def make_engine(core_http, clock, llm=None, mono=None):
    kw = {"mono": mono} if mono else {}
    return TurnEngine(CoreClient(core_http), llm, clock=clock, **kw)


def explode_if_called(req: httpx.Request) -> httpx.Response:
    raise AssertionError("the LLM must never be involved in a delivery")


@pytest.fixture()
def eng(core_http):
    clock = Clock()
    return make_engine(core_http, clock), clock


def deliveries(core_http, uid):
    return core_http.get(f"/users/{uid}/deliveries").json()


def pending(core_http, uid):
    return core_http.get(f"/users/{uid}/actions/pending").json()


# ---- rendering: fixed templates straight from SQL -----------------------------------------------------------
def test_a_medicine_prompt_is_the_fixed_template_with_name_dose_and_time_verbatim(core_http, uid, eng):
    engine, _ = eng
    add_medicine(core_http, uid)
    tick(core_http)
    item = engine.deliver_next(uid, "s1")
    assert item["screen"] == "medicine" and item["kind"] == "medicine" and item["awaiting_confirmation"] is True
    assert item["text"] == MR["deliver_medicine"].format(name="टेल्मा सकाळ", dose=DOSE, when=rp.say_time("09:00", "mr"))
    assert "टेल्मा सकाळ" in item["text"] and DOSE in item["text"]
    assert item["item"].startswith("dose:")


def test_the_medicine_question_is_a_real_pending_action_so_one_spoken_yes_confirms_it(core_http, uid, eng):
    engine, _ = eng
    add_medicine(core_http, uid)
    tick(core_http)
    engine.deliver_next(uid, "s1")
    p = pending(core_http, uid)
    assert p["action_type"] == "MEDICINE_TAKEN"


def test_a_reminder_is_spoken_as_its_task_verbatim_and_a_late_one_says_when_it_was_due(core_http, uid, eng):
    engine, clock = eng
    set_core_now(core_http, NOW)
    core_http.post(f"/users/{uid}/reminders", json={"task": "डॉक्टरांकडे जायचं", "date": "2026-10-06", "time": "09:05"})
    tick(core_http, NOW + timedelta(minutes=5, seconds=10))
    clock.now = NOW + timedelta(minutes=5, seconds=10)
    on_time = engine.deliver_next(uid, "s1")
    assert on_time["text"] == "आठवण: डॉक्टरांकडे जायचं." and on_time["screen"] == "reminder"
    assert on_time["awaiting_confirmation"] is False and on_time["item"].startswith("reminder:")
    # the same reminder, spoken half an hour later (nobody was there): it says when it was due
    engine.deliver_release(uid, on_time["delivery_id"], "s1", "interrupted")
    set_core_now(core_http, NOW + timedelta(minutes=35))
    clock.now = NOW + timedelta(minutes=35)
    late = engine.deliver_next(uid, "s1")
    assert late["text"] == MR["deliver_reminder_late"].format(when=rp.say_time("09:05", "mr"), task="डॉक्टरांकडे जायचं")


def test_no_llm_call_is_ever_made_for_a_delivery(core_http, uid):
    llm = EvonClient("https://llm.test/v1", "m", http=httpx.Client(transport=httpx.MockTransport(explode_if_called)),
                     schema=load_intent_schema())
    engine = make_engine(core_http, Clock(), llm)
    add_medicine(core_http, uid)
    tick(core_http)
    assert engine.deliver_next(uid, "s1") is not None


def test_nothing_waiting_gives_nothing(core_http, uid, eng):
    assert eng[0].deliver_next(uid, "s1") is None


# ---- when it must NOT speak ----------------------------------------------------------------------------------
def test_it_waits_while_a_yes_no_question_is_pending_and_the_item_stays_queued(core_http, uid, eng):
    engine, _ = eng
    add_medicine(core_http, uid)
    tick(core_http)
    engine.handle(uid, "उद्या सकाळी दहा वाजता डॉक्टरकडे जायचं आहे आठवण कर मला")  # leaves a pending reminder
    assert engine.deliver_next(uid, "s1") is None
    assert [d["status"] for d in deliveries(core_http, uid)] == ["queued"]  # not claimed, not lost
    assert pending(core_http, uid)["action_type"] == "CREATE_REMINDER"  # and the question was not replaced
    engine.handle(uid, "नको")
    assert engine.deliver_next(uid, "s1") is not None


def test_it_never_talks_over_a_safety_reply_and_holds_for_two_minutes(core_http, uid):
    clock, mono = Clock(), {"t": 1000.0}
    engine = make_engine(core_http, clock, mono=lambda: mono["t"])
    add_medicine(core_http, uid)
    tick(core_http)
    assert engine.handle(uid, "मला छातीत दुखतंय").mode == "safety"
    assert engine.deliver_next(uid, "s1") is None
    mono["t"] += 100
    assert engine.deliver_next(uid, "s1") is None
    mono["t"] += 30
    assert engine.deliver_next(uid, "s1") is not None


def test_two_open_sessions_can_never_get_the_same_item(core_http, uid, eng):
    engine, _ = eng
    add_medicine(core_http, uid)
    tick(core_http)
    first = engine.deliver_next(uid, "A")
    assert first is not None and engine.deliver_next(uid, "B") is None


# ---- spoken / release are passed through, never decided here ---------------------------------------------------
def test_spoken_and_release_reach_the_queue(core_http, uid, eng):
    engine, _ = eng
    set_core_now(core_http, NOW)
    core_http.post(f"/users/{uid}/reminders", json={"task": "tea", "date": "2026-10-06", "time": "09:05"})
    tick(core_http, NOW + timedelta(minutes=5, seconds=5))
    item = engine.deliver_next(uid, "A")
    engine.deliver_release(uid, item["delivery_id"], "A", "tts")
    assert deliveries(core_http, uid)[0]["fail_count"] == 1
    again = engine.deliver_next(uid, "A")
    engine.deliver_spoken(uid, again["delivery_id"], "A")
    assert deliveries(core_http, uid)[0]["status"] == "spoken"


def test_busy_reports_pending_safety_hold_and_waiting(core_http, uid, eng):
    engine, _ = eng
    assert engine.busy(uid) == {"pending": False, "safety_hold": False, "queued": 0}
    add_medicine(core_http, uid)
    tick(core_http)
    assert engine.busy(uid)["queued"] == 1
    engine.deliver_next(uid, "s1")
    assert engine.busy(uid)["pending"] is True


# ---- answering the medicine question ---------------------------------------------------------------------------
def delivered_medicine(core_http, uid, engine):
    add_medicine(core_http, uid)
    tick(core_http)
    item = engine.deliver_next(uid, "s1")
    engine.deliver_spoken(uid, item["delivery_id"], "s1")
    return item


def dose_history(core_http, uid):
    return core_http.get(f"/users/{uid}/medicine-doses").json()


@pytest.mark.parametrize("answer", ["हो", "घेतली", "होय घेतली", "ghetli", "ho"])
def test_a_yes_or_ghetli_marks_it_taken_and_acknowledges_the_delivery(core_http, uid, eng, answer):
    engine, _ = eng
    delivered_medicine(core_http, uid, engine)
    res = engine.handle(uid, answer)
    assert res.intent == "CONFIRM_YES", answer
    assert dose_history(core_http, uid)[0]["status"] == "taken"
    d = deliveries(core_http, uid)[0]
    assert (d["status"], d["outcome"]) == ("acknowledged", "taken")


@pytest.mark.parametrize("answer", ["नाही", "घेतली नाही", "नको"])
def test_no_is_recorded_as_not_taken_with_no_advice_and_no_nagging(core_http, uid, eng, answer):
    engine, clock = eng
    delivered_medicine(core_http, uid, engine)
    res = engine.handle(uid, answer)
    assert res.reply == MR["med_not_taken_ack"] and res.screen != "confirm"
    assert "डॉक्टर" not in res.reply and "घ्या" not in res.reply  # no advice, no "take it now"
    assert dose_history(core_http, uid)[0]["status"] == "not_taken"
    assert [n["kind"] for n in core_http.get(f"/users/{uid}/notifications").json()] == ["medicine_not_taken"]
    tick(core_http, NOW + timedelta(minutes=20))  # the next ticks queue nothing for this dose
    assert engine.deliver_next(uid, "s1") is None


@pytest.mark.parametrize("answer", ["नंतर", "थोड्या वेळाने", "later"])
def test_later_is_an_answer_to_the_medicine_question_and_asks_to_snooze(core_http, uid, eng, answer):
    engine, _ = eng
    delivered_medicine(core_http, uid, engine)
    res = engine.handle(uid, answer)
    assert res.intent == "MED_SNOOZE" and res.awaiting_confirmation
    assert pending(core_http, uid)["action_type"] == "MEDICINE_SNOOZE"
    assert engine.handle(uid, "हो").intent == "CONFIRM_YES"
    assert dose_history(core_http, uid)[0]["status"] == "reminded"  # snoozed, not taken


def test_no_to_the_self_started_record_it_question_is_not_a_not_taken(core_http, uid, eng):
    """Different question: the elder said "ghetli" and Arjun asked "record it as taken?". A no means do not
    record, NOT that the dose was missed."""
    engine, _ = eng
    add_medicine(core_http, uid)
    tick(core_http)
    engine.handle(uid, "ghetli")  # no delivery involved
    res = engine.handle(uid, "nahi")
    assert res.reply == MR["cancelled"]
    assert dose_history(core_http, uid)[0]["status"] != "not_taken"
    assert core_http.get(f"/users/{uid}/notifications").json() == []


def test_unrelated_talk_repeats_the_medicine_question_with_the_exact_wording(core_http, uid, eng):
    engine, _ = eng
    item = delivered_medicine(core_http, uid, engine)
    res = engine.handle(uid, "आज काय आहे")
    assert res.intent == "PENDING_REPEAT" and res.awaiting_confirmation
    assert res.reply == item["text"]  # name, dose and time again, verbatim
    assert pending(core_http, uid)["action_type"] == "MEDICINE_TAKEN"


def test_no_answer_before_the_expiry_leaves_the_existing_family_notice_rule_to_decide(core_http, uid, eng):
    engine, _ = eng
    delivered_medicine(core_http, uid, engine)
    from core_api import models as m
    from core_api.db import get_db
    from core_api.main import app

    session = next(app.dependency_overrides[get_db]())
    row = session.get(m.PendingAction, pending(core_http, uid)["id"])
    row.created_at = NOW - timedelta(minutes=6)  # asked six minutes ago: past the 5 minute expiry
    session.commit()
    assert pending(core_http, uid) is None
    assert dose_history(core_http, uid)[0]["status"] == "reminded"  # nothing recorded for the elder
    assert engine.handle(uid, "हो").reply == MR["nothing_pending"]  # a late yes confirms nothing


def test_a_safety_reply_clears_the_medicine_question_without_recording_not_taken(core_http, uid, eng):
    engine, _ = eng
    delivered_medicine(core_http, uid, engine)
    assert engine.handle(uid, "मला छातीत दुखतंय").mode == "safety"
    assert dose_history(core_http, uid)[0]["status"] == "reminded"
    assert core_http.get(f"/users/{uid}/notifications").json()[0]["kind"] == "emergency"
