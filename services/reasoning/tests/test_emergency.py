"""Physical emergency path. The lexicon is UNVERIFIED (written without a native speaker); these
tests pin behaviour, they do not prove recall on real speech."""

import httpx
import pytest
from reasoning_svc.core_client import CoreClient
from reasoning_svc.distress import is_distress, is_emergency
from reasoning_svc.turn import TurnEngine

EMERGENCY = [
    "छातीत दुखतंय", "मला छातीत दुखतंय", "श्वास घेता येत नाही", "दम लागतोय", "मी पडले",
    "मी पडलो आहे", "उठता येत नाही", "चक्कर येतेय", "chhatit dukhtay", "mi padle", "uthta yet nahi",
    "सीने में दर्द हो रहा है", "मैं गिर गई", "saans nahi le pa raha", "chest pain", "I can't breathe",
    "I fell", "I have fallen and can't get up", "call ambulance",
]
NOT_EMERGENCY = [
    "मी लहानपणी झाडावरून पडले होते",  # a childhood story, past perfect
    "mi lahanpani padle hote",
    "udya doctor la jaycha aahe remind kar",
    "आज काय आहे",
    "mala chaha pahije",
    "my grandson fell in love",
]


@pytest.mark.parametrize("text", EMERGENCY)
def test_emergency_detected(text):
    assert is_emergency(text)


@pytest.mark.parametrize("text", NOT_EMERGENCY)
def test_no_false_emergency(text):
    assert not is_emergency(text)


def test_emergency_reply_and_overrides_pending(engine, core_http, uid):
    engine.handle(uid, "udya 19:30 vajta doctor remind kar")  # leaves a pending action
    assert core_http.get(f"/users/{uid}/actions/pending").json() is not None
    res = engine.handle(uid, "मला छातीत दुखतंय")
    assert res.intent == "EMERGENCY" and res.mode == "safety"
    assert "११२" in res.reply or "112" in res.reply
    assert core_http.get(f"/users/{uid}/actions/pending").json() is None
    engine.handle(uid, "ho")  # a stray yes must not create the reminder
    assert core_http.get(f"/users/{uid}/reminders").json() == []


def test_emergency_takes_priority_over_distress(engine, uid):
    text = "chest pain, i am scared"
    assert is_distress(text) and is_emergency(text)
    assert engine.handle(uid, text).intent == "EMERGENCY"


def test_emergency_reply_never_diagnoses(engine, uid):
    reply = engine.handle(uid, "chest pain").reply.lower()
    for bad in ("heart attack", "you have", "diagnos", "it is nothing", "don't worry"):
        assert bad not in reply


def test_detected_english_emergency_keeps_english_safety_wording(engine, uid):
    result = engine.handle(uid, "chest pain", "en-IN")
    assert result.language == "en" and "call 112" in result.reply


def _down_engine():
    def down(request):
        raise httpx.ConnectError("core-api down", request=request)

    http = httpx.Client(transport=httpx.MockTransport(down), base_url="http://core")
    return TurnEngine(CoreClient(http), evon=None)


def test_emergency_reply_survives_core_api_failure():
    res = _down_engine().handle(1, "छातीत दुखतंय")
    assert res.intent == "EMERGENCY" and ("११२" in res.reply or "112" in res.reply)


def test_core_api_down_gives_spoken_error_not_exception():
    """A normal turn with core-api unreachable must return the fixed error template (no 500)."""
    res = _down_engine().handle(1, "aaj kay aahe")
    assert res.intent == "UNKNOWN" and res.reply
