"""A pending action can only be answered, corrected, or cancelled (fix B, from the live T6 test).

Boundary 1: only a spoken yes executes an action; and a "हो" must never confirm something other than what was
asked. At 17:15 a pending reminder was silently replaced by a "keep your story?" question.
"""

import pytest
from reasoning_svc import replies as rp

MR = rp.R["mr"]
DOCTOR = "उद्या सकाळी दहा वाजता डॉक्टरकडे जायचं आहे आठवण कर मला"
LONG_CHAT = "आज मी बागेत फिरायला गेलो होतो आणि तिथे खूप जुने मित्र भेटले आम्ही खूप गप्पा मारल्या आणि चहा प्यायलो"


def pending(core_http, uid):
    return core_http.get(f"/users/{uid}/actions/pending").json()


def actions(core_http, uid):
    """Every proposal ever made for this user (a story-save would show up here as SAVE_STORY)."""
    from core_api import models as m
    from core_api.db import get_db
    from core_api.main import app
    from sqlalchemy import select

    session = next(app.dependency_overrides[get_db]())
    return [(a.id, a.action_type, a.status) for a in session.scalars(select(m.PendingAction).where(m.PendingAction.user_id == uid))]


def test_a_long_chat_sentence_does_not_replace_a_pending_reminder(engine, core_http, uid):
    engine.handle(uid, DOCTOR)
    before = pending(core_http, uid)
    res = engine.handle(uid, LONG_CHAT)
    assert res.intent == "PENDING_REPEAT" and res.awaiting_confirmation and res.screen == "confirm"
    assert "10:00" in res.reply and res.reply.rstrip().endswith("हो किंवा नाही सांगा.")  # the question again
    assert pending(core_http, uid) == before  # same id, same payload, still pending
    assert [a[1] for a in actions(core_http, uid)] == ["CREATE_REMINDER"]  # no story-save was ever proposed


@pytest.mark.parametrize(
    "text",
    [
        "आज काय आहे",
        "उद्या काय आहे",
        "मदत",
        "छान",
        "kiti vajle",
        "हॅलो",
        "ऐकू येतंय का",
        "औषधाबद्दल विचारायचं आहे दोन गोळ्या घेऊ का",
        "ही गोष्ट कुटुंबाला सांग",
        "water plants zala",
        "हं",
        "आज मी बागेत फिरायला गेलो होतो खूप छान वाटलं",
    ],
)
def test_nothing_but_yes_no_or_a_correction_moves_a_pending_reminder(engine, core_http, uid, text):
    engine.handle(uid, DOCTOR)
    before = pending(core_http, uid)
    res = engine.handle(uid, text)
    assert res.intent == "PENDING_REPEAT" and res.awaiting_confirmation, text
    assert pending(core_http, uid) == before, text
    assert [a[1] for a in actions(core_http, uid)] == ["CREATE_REMINDER"], text


def test_a_pending_story_save_is_repeated_not_replaced(engine, core_http, uid):
    engine.handle(uid, LONG_CHAT)  # no pending yet: this offers to keep the story
    assert pending(core_http, uid)["action_type"] == "SAVE_STORY"
    res = engine.handle(uid, "आज काय आहे")
    assert res.intent == "PENDING_REPEAT" and MR["ask_save_story"] in res.reply
    assert pending(core_http, uid)["action_type"] == "SAVE_STORY"


def test_a_pending_caregiver_request_is_repeated(engine, core_http, uid):
    engine.handle(uid, "mala madat pahije")
    first = pending(core_http, uid)
    res = engine.handle(uid, LONG_CHAT)
    assert res.intent == "PENDING_REPEAT" and MR["confirm_caregiver"] in res.reply
    assert pending(core_http, uid) == first


def test_restating_the_reminder_is_a_correction_and_replaces_it(engine, core_http, uid):
    engine.handle(uid, DOCTOR)
    res = engine.handle(uid, "उद्या सकाळी अकरा वाजता डॉक्टरकडे जायचं आहे आठवण कर")
    assert res.intent == "CREATE_REMINDER" and "11:00" in res.reply
    now_pending = pending(core_http, uid)
    assert now_pending["payload"]["time"] == "11:00" and now_pending["action_type"] == "CREATE_REMINDER"


def test_yes_no_and_cancel_still_work(engine, core_http, uid):
    engine.handle(uid, DOCTOR)
    assert engine.handle(uid, "हो").intent == "CONFIRM_YES"
    engine.handle(uid, DOCTOR)
    assert engine.handle(uid, "नको").intent == "CONFIRM_NO"
    engine.handle(uid, DOCTOR)
    assert engine.handle(uid, "आज नको").intent == "DECLINE_TOPIC"
    assert pending(core_http, uid) is None


def test_asking_who_arjun_is_still_answered_and_leaves_the_pending_action(engine, core_http, uid):
    engine.handle(uid, DOCTOR)
    before = pending(core_http, uid)
    res = engine.handle(uid, "तू माणूस आहेस का")
    assert res.reply == MR["ai_disclosure"] and pending(core_http, uid) == before


def test_an_emergency_still_wins_over_a_pending_action(engine, core_http, uid):
    engine.handle(uid, DOCTOR)
    assert engine.handle(uid, "मला छातीत दुखतंय").mode == "safety"
    assert pending(core_http, uid) is None


# ---- the "keep your story?" offer: companion talk only ---------------------------------------------------
def test_a_real_story_is_still_offered_to_be_kept(engine, core_http, uid):
    res = engine.handle(uid, LONG_CHAT)
    assert res.mode == "companion" and res.awaiting_confirmation
    assert pending(core_http, uid)["action_type"] == "SAVE_STORY"


def test_recognizer_junk_is_never_offered_as_a_story(engine, core_http, uid):
    junk = "हो कर नाही कर हो नाही कर हो हो नाही कर कर हो नाही हो कर नाही हो कर"  # 20 words, 3 distinct
    res = engine.handle(uid, junk)
    assert not res.awaiting_confirmation and pending(core_http, uid) is None


def test_an_open_reminder_draft_is_never_turned_into_a_story_offer(engine, core_http, uid):
    engine.handle(uid, "udya doctor la jaycha aahe, remind kar")  # asks for the time: a draft is open
    engine.handle(uid, LONG_CHAT)
    assert all(a[1] != "SAVE_STORY" for a in actions(core_http, uid))


def test_a_long_care_command_is_a_care_command_not_a_story(engine, core_http, uid):
    long_care = "उद्या सकाळी दहा वाजता मला डॉक्टरकडे जायचं आहे कृपया मला आठवण कर आणि मुलाला पण सांग की मी जाणार आहे"
    res = engine.handle(uid, long_care)
    assert res.mode == "care" and pending(core_http, uid)["action_type"] == "CREATE_REMINDER"
