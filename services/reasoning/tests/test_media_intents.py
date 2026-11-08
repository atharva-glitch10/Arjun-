"""Media / app intents: the two real elder-screen transcripts that fell through to the companion LLM, the three
sentences that must stay chat, and the priorities (safety first, reminders still reminders).

Lexicon is UNVERIFIED (no native-speaker review). Real core-api in memory; no network.
"""

from datetime import datetime

import pytest
from reasoning_svc.appcmd import parse_app_command
from reasoning_svc.core_client import CoreClient
from reasoning_svc.evon import sanitize_companion
from reasoning_svc.turn import TurnEngine

NOW = datetime(2026, 10, 6, 9, 0)
CHANNEL = "UCZFMm1mMw0F81Z37aaEzTUA"


class NoLlm:
    """Any call from the rules-unreadable path fails the test: these turns must be decided by the rules."""

    def extract_intent(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("this turn must not reach the LLM")


def engine(core_http, llm=None):
    return TurnEngine(CoreClient(core_http), llm, clock=lambda: NOW, ask_first=False)


def link(core_http, uid, **body):
    r = core_http.post(f"/users/{uid}/app-links", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ---- the two bug sentences ----------------------------------------------------------------------------------------
def test_news_on_screen_is_an_open_media_command_and_never_reaches_the_llm(core_http, uid):
    link(core_http, uid, kind="youtube_channel_live", label="मराठी बातम्या", value=CHANNEL)
    res = engine(core_http, NoLlm()).handle(uid, "मला बातम्या बघायच्या")
    assert res.intent == "OPEN_MEDIA"
    assert res.reply == "बातम्या लावतो."
    assert res.action["type"] == "open" and res.action["kind"] == "youtube_channel_live"
    assert parse_app_command("मला बातम्या बघायच्या").topic == "news_video"


def test_youtube_link_is_an_open_media_command_and_never_reaches_the_llm(core_http, uid):
    res = engine(core_http, NoLlm()).handle(uid, "नाही मला तू यूट्यूब व्हिडिओची लिंक दे")
    assert res.intent == "OPEN_MEDIA"
    assert res.reply == "काय बघायचं आहे — बातम्या, गाणी की रेसिपी?" and res.action["type"] == "none"
    cmd = parse_app_command("नाही मला तू यूट्यूब व्हिडिओची लिंक दे")
    assert cmd.topic == "youtube" and cmd.query == ""  # a pointer is not a search


# ---- a named singer / bhajan --------------------------------------------------------------------------------------
def test_a_named_bhajan_keeps_the_singers_name_in_the_query(core_http, uid, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)  # no search: the results page opens for the cleaned query
    res = engine(core_http).handle(uid, "भीमसेन जोशींचं भजन लावा")
    assert res.intent == "OPEN_MEDIA"
    assert res.action["type"] == "open"
    assert "भीमसेन जोशी" in res.action["title"]


# ---- news read aloud ----------------------------------------------------------------------------------------------
def test_news_read_aloud_is_news_read(core_http, uid):
    res = engine(core_http).handle(uid, "बातम्या ऐकवा")
    assert res.intent == "NEWS_READ"


# ---- WhatsApp: the contact's id, never a guessed name -------------------------------------------------------------
def test_whatsapp_matches_a_contact_and_returns_its_id(core_http, uid):
    c = core_http.post(f"/users/{uid}/contacts", json={"name": "चंद्रकांत", "phone": "9000000001"}).json()
    link(core_http, uid, kind="whatsapp", label="चंद्रकांत", value=str(c["id"]))
    res = engine(core_http).handle(uid, "चंद्रकांतला व्हॉट्सॲप कर")
    assert res.intent == "OPEN_WHATSAPP"
    assert res.action["kind"] == "whatsapp" and res.action["contact_id"] == str(c["id"])


# ---- controls -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("said", ["अर्जुन थांबव", "बंद कर"])
def test_media_control_stop(core_http, uid, said):
    res = engine(core_http).handle(uid, said)
    assert res.intent == "MEDIA_CONTROL"
    assert res.reply == "बंद केलं."
    assert res.action["type"] == "control" and res.action["kind"] == "stop"


# ---- these are talk, not commands ---------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "said",
    [
        "मला गाणं आठवलं, लहानपणी आम्ही गायचो",
        "काल बातम्यांमध्ये पाऊस होता असं ऐकलं",
        "माझ्या नातवाने यूट्यूबवर काम केलं",  # mentions YouTube, asks for nothing
    ],
)
def test_stories_stay_chat(core_http, uid, said):
    assert engine(core_http).handle(uid, said).intent == "CHAT"


# ---- priorities ---------------------------------------------------------------------------------------------------
def test_safety_still_wins_over_a_media_request(core_http, uid):
    res = engine(core_http).handle(uid, "छातीत दुखतंय, यूट्यूब लाव")
    assert res.intent == "EMERGENCY" and res.mode == "safety"


def test_a_reminder_that_mentions_media_is_still_a_reminder(core_http, uid):
    res = engine(core_http).handle(uid, "उद्या सकाळी दहा वाजता डॉक्टरची आठवण ठेव")
    assert res.intent == "CREATE_REMINDER"


# ---- the turn is remembered, so the chat can go on ----------------------------------------------------------------
def test_a_media_turn_enters_the_conversation_history(core_http, uid):
    eng = engine(core_http)
    eng.handle(uid, "नाही मला तू यूट्यूब व्हिडिओची लिंक दे")
    assert any("यूट्यूब" in text for role, text in eng.memory.view(uid, NOW).messages if role == "user")


# ---- the companion may not refuse and change the subject ----------------------------------------------------------
@pytest.mark.parametrize(
    "said",
    [
        "मला बातम्या बघता येत नाहीत, पण तुमची आजची सकाळ कशी गेली?",
        "मला यूट्यूब व्हिडिओची लिंक देता येत नाही, पण अनारसे कसे बनवायचे ते शिकवाल का?",
        "I can't do that, but tell me about your garden.",
    ],
)
def test_a_refusal_is_not_a_sanitizer_violation(said):
    text, reasons = sanitize_companion(said, "mr" if not said.isascii() else "en")
    assert text == said
    assert reasons == []
