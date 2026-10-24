"""Invariant behind the voice agent's stale-reply rule.

The agent may drop an outdated plain reply, but never one that asks for a yes/no. That is only safe
if EVERY reply that leaves a pending action in core-api is flagged awaiting_confirmation, and if safety
replies are labelled mode "safety". If either slips, a later spoken "yes" could confirm something the
user never heard (CLAUDE.md boundary 1).
"""

import pytest

DOCTOR = "उद्या सकाळी दहा वाजता डॉक्टरकडे जायचं आहे आठवण कर मला"
LONG_STORY = "mi lahanpani gavat khup khelayche ani amhi roj nadivar jaycho mag aaji amhala bhakri dayachi ani goshti sangaychi"


def _pending(core_http, uid):
    return core_http.get(f"/users/{uid}/actions/pending").json()


def _reminder(core_http, uid):
    core_http.post(f"/users/{uid}/reminders", json={"task": "water plants", "date": "2026-10-06", "time": "09:00"})


def _story(engine, core_http, uid):
    engine.handle(uid, LONG_STORY)
    engine.handle(uid, "ho")  # saved privately


@pytest.mark.parametrize(
    "setup,text",
    [
        (None, DOCTOR),  # CREATE_REMINDER
        (None, "udya 19:30 vajta doctor remind kar"),
        (None, "mala madat pahije"),  # REQUEST_CAREGIVER
        (None, LONG_STORY),  # SAVE_STORY
        ("reminder", "water plants zala"),  # COMPLETE_REMINDER
        ("story", "hi goshta kutumbala sang"),  # SHARE_STORY
        (None, "औषधाबद्दल विचारायचं आहे दोन गोळ्या घेऊ का"),  # medicine question -> caregiver offer
    ],
)
def test_every_reply_that_leaves_a_pending_action_asks_for_confirmation(engine, core_http, uid, setup, text):
    if setup == "reminder":
        _reminder(core_http, uid)
    elif setup == "story":
        _story(engine, core_http, uid)
    res = engine.handle(uid, text)
    if _pending(core_http, uid) is not None:
        assert res.awaiting_confirmation, f"pending action stored but reply is not flagged: {res.reply!r}"


def test_a_pending_action_is_always_found_for_the_main_flows(engine, core_http, uid):
    """Guards the test above against passing vacuously: these flows must actually create a pending action."""
    res = engine.handle(uid, DOCTOR)
    assert _pending(core_http, uid) is not None and res.awaiting_confirmation
    engine.handle(uid, "नको")
    res = engine.handle(uid, "mala madat pahije")
    assert _pending(core_http, uid) is not None and res.awaiting_confirmation


@pytest.mark.parametrize("text", ["मला छातीत दुखतंय", "mala jagaychi iccha nahi"])
def test_emergency_and_distress_replies_are_labelled_safety(engine, uid, text):
    assert engine.handle(uid, text).mode == "safety"


def test_a_yes_after_a_safety_reply_confirms_nothing(engine, core_http, uid):
    engine.handle(uid, DOCTOR)  # leaves a pending reminder
    engine.handle(uid, "मला छातीत दुखतंय")  # emergency clears it
    engine.handle(uid, "ho")
    assert core_http.get(f"/users/{uid}/reminders").json() == []
