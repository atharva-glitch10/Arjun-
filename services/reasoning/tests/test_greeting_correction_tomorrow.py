"""Greeting, hearing check, correction while a confirmation is pending, and "tomorrow" listings.

All from the first real-speech test (2026-10-24): "हॅलो" was "not understood", "can you hear me" got a
canned story prompt, a correction to a pending reminder was treated as chat, and "उद्या काय आहे" could
only ever list today.
"""

import pytest
from reasoning_svc import replies as rp

MR = rp.R["mr"]
DOCTOR = "उद्या सकाळी दहा वाजता डॉक्टरकडे जायचं आहे आठवण कर मला"


def _pending(core_http, uid):
    return core_http.get(f"/users/{uid}/actions/pending").json()


# ---- greeting -----------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["हॅलो", "हेलो", "नमस्कार", "नमस्ते", "hello", "Hello!", "namaste", "namaskar"])
def test_greeting_gets_a_fixed_greeting_not_an_error(engine, core_http, uid, text):
    res = engine.handle(uid, text)
    assert res.intent == "GREETING" and res.mode == "care" and not res.awaiting_confirmation
    assert res.reply in (MR["greet"], rp.R["hi"]["greet"], rp.R["en"]["greet"])
    assert _pending(core_http, uid) is None


def test_greeting_followed_by_a_request_is_the_request(engine, uid):
    res = engine.handle(uid, "हॅलो आज काय आहे")
    assert res.intent == "LIST_TODAY"


# ---- hearing check ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    ["हां आता ऐकू येतंय का तुला", "ऐकू येतंय का", "तुला ऐकू येतं का", "अर्जुन ऐकू येतंय ना", "ऐकतोस का"],
)
def test_hearing_check_answers_yes_i_can_hear_you(engine, text, uid):
    res = engine.handle(uid, text)
    assert res.intent == "HEARING_CHECK" and not res.awaiting_confirmation
    assert res.reply == "हो, मला ऐकू येतंय."


def test_hearing_check_in_hindi_and_english(engine, uid):
    assert engine.handle(uid, "क्या तुम्हें सुनाई दे रहा है").reply == rp.R["hi"]["hearing_ok"]
    assert engine.handle(uid, "can you hear me").reply == rp.R["en"]["hearing_ok"]


def test_hearing_check_does_not_drop_an_open_reminder(engine, core_http, uid):
    engine.handle(uid, "udya doctor la jaycha aahe, remind kar")  # no time yet: draft is open
    assert engine.handle(uid, "ऐकू येतंय का").intent == "HEARING_CHECK"
    res = engine.handle(uid, "सकाळी दहा वाजता")
    assert res.intent == "CREATE_REMINDER" and "10:00" in res.reply


# ---- correction while a confirmation is pending ---------------------------------------------------
CORRECTION = "सकाळी दहा वाजता डॉक्टरकडे जायचं आहे दहा डॉक्टरांकडे नाही जायचं"  # real Prisma transcript


def test_long_no_while_a_reminder_is_pending_cancels_it_and_asks_again(engine, core_http, uid):
    engine.handle(uid, DOCTOR)
    assert _pending(core_http, uid) is not None
    res = engine.handle(uid, CORRECTION)
    assert res.intent == "CONFIRM_NO" and res.reply == MR["cancelled_retry"]
    assert _pending(core_http, uid) is None  # rejected, nothing saved
    assert core_http.get(f"/users/{uid}/reminders").json() == []


def test_long_sentence_with_no_pending_action_is_not_a_cancellation(engine, uid):
    res = engine.handle(uid, CORRECTION)
    assert res.intent == "CHAT"


def test_a_story_with_a_no_in_it_does_not_reject_the_pending_save(engine, core_http, uid):
    core_http.post(
        f"/users/{uid}/actions/propose",
        json={"action_type": "SAVE_STORY", "payload": {"summary": "x"}},
    )
    res = engine.handle(uid, "तेव्हा आम्ही गावाला गेलो होतो पण तिथे कोणीच नाही भेटलं आणि मग परत आलो")
    assert res.intent != "CONFIRM_NO"
    assert _pending(core_http, uid) is not None


def test_bare_no_keeps_the_old_cancel_reply(engine, core_http, uid):
    engine.handle(uid, DOCTOR)
    res = engine.handle(uid, "नको")
    assert res.intent == "CONFIRM_NO" and res.reply == MR["cancelled"]


# ---- tomorrow ----------------------------------------------------------------------------------
def _seed(core_http, uid):
    core_http.post(f"/users/{uid}/reminders", json={"task": "doctor visit", "date": "2026-10-07", "time": "10:00"})
    core_http.post(f"/users/{uid}/reminders", json={"task": "call Rahul", "date": "2026-10-06", "time": "16:00"})


def test_tomorrow_lists_tomorrows_items_from_sql(engine, core_http, uid):
    _seed(core_http, uid)
    res = engine.handle(uid, "उद्या काय आहे")
    assert res.intent == "LIST_TODAY" and res.mode == "care"
    assert res.reply.startswith("उद्या तुमच्याकडे:")
    assert "doctor visit" in res.reply and "10:00" in res.reply and "call Rahul" not in res.reply


def test_today_still_lists_only_today(engine, core_http, uid):
    _seed(core_http, uid)
    res = engine.handle(uid, "आज काय आहे")
    assert res.reply.startswith("आज तुमच्याकडे:") and "call Rahul" in res.reply and "doctor visit" not in res.reply


def test_tomorrow_with_nothing_says_so(engine, uid):
    assert engine.handle(uid, "उद्या काय आहे").reply == "उद्या तुमच्यासाठी कोणतीही आठवण नाही."


def test_today_and_tomorrow_in_one_sentence_asks_which_day(engine, core_http, uid):
    _seed(core_http, uid)
    res = engine.handle(uid, "उद्या आज काय आहे")  # real Prisma transcript: ambiguous, never guess
    assert res.reply == MR["ask_date"] and "doctor visit" not in res.reply and "call Rahul" not in res.reply


def test_tomorrow_in_hindi_and_english(engine, core_http, uid):
    _seed(core_http, uid)
    assert "doctor visit" in engine.handle(uid, "कल क्या है").reply
    assert "doctor visit" in engine.handle(uid, "my reminders tomorrow").reply
