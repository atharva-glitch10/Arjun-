"""Conversation mode (2026-10-31): once a companion chat is going, odd, short or ambiguous turns stay in the
chat. Built from the transcripts of the 22:47 live session (synthetic data only).

Safety and explicit care commands still win; both the no-question mode and ask-first keep working."""

import json
from datetime import datetime

import httpx
import pytest
from reasoning_svc.core_client import CoreClient
from reasoning_svc.evon import EvonClient, load_intent_schema
from reasoning_svc.turn import TurnEngine

NOW = datetime(2026, 10, 6, 9, 0)  # the conftest clock
REPLY = "छान वाटलं. मग पुढे काय झालं?"
CHICKEN = "अथर्वनी आज चिकन बनवलं होतं चिकन खूप छान झालं होतं आणि मी चपाती आणि भात"
OPENING = "आज मी बागेत गेले होते आणि मला खूप छान वाटलं"  # >= 5 words: a plain CHAT turn


class Llm:
    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        body["_purpose"] = "intent" if body["temperature"] == 0.0 else "companion"
        self.calls.append(body)
        if body["_purpose"] == "intent":
            content = json.dumps({"intent": "CHAT", "confidence": 0.9, "language": "mr"})
        else:
            content = REPLY
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    @property
    def purposes(self):
        return [c["_purpose"] for c in self.calls]


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def make(core_http, *, llm=True, ask_first=False):
    fake = Llm()
    client = None
    if llm:
        http = httpx.Client(transport=httpx.MockTransport(fake))
        client = EvonClient("https://llm.test/v1", "m", http=http, schema=load_intent_schema(), provider="TestAI")
    clock = Clock()
    eng = TurnEngine(CoreClient(core_http), client, clock=lambda: NOW, ask_first=ask_first, mono=clock)
    return eng, fake, clock


def add_reminder(core_http, uid, task="डॉक्टरांकडे जायचं", time="09:30"):
    r = core_http.post(f"/users/{uid}/reminders", json={"task": task, "date": "2026-10-06", "time": time})
    assert r.status_code == 201
    return r.json()


def reminder_status(core_http, uid):
    return [x["status"] for x in core_http.get(f"/users/{uid}/reminders").json()]


@pytest.fixture()
def talking(core_http, uid):
    """An engine that is already mid-conversation (one companion turn done)."""
    eng, fake, clock = make(core_http)
    first = eng.handle(uid, OPENING)
    assert first.intent == "CHAT" and first.mode == "companion"
    return eng, fake, clock


# ---- evidence 1: "झालं" in a story is not "mark my reminder done" -----------------------------------------------
def test_a_story_sentence_with_zala_is_chat_in_conversation(talking, core_http, uid):
    eng, fake, _ = talking
    add_reminder(core_http, uid)
    res = eng.handle(uid, CHICKEN)
    assert res.intent == "CHAT" and res.mode == "companion"
    assert "पूर्ण करायची" not in res.reply
    assert reminder_status(core_http, uid) == ["pending"]


def test_zala_na_in_conversation_is_chat(talking, core_http, uid):
    eng, _, _ = talking
    add_reminder(core_http, uid)
    res = eng.handle(uid, "झाला ना")
    assert res.intent == "CHAT" and res.reply == REPLY
    assert reminder_status(core_http, uid) == ["pending"]


def test_the_story_is_not_a_completion_outside_conversation_either(core_http, uid):
    eng, _, _ = make(core_http)
    add_reminder(core_http, uid)
    res = eng.handle(uid, CHICKEN)  # no conversation yet; nothing matches the open reminder
    assert res.intent == "CHAT"
    assert reminder_status(core_http, uid) == ["pending"]


def test_no_open_reminder_at_all_is_chat_not_nothing_to_complete(core_http, uid):
    eng, _, _ = make(core_http)
    res = eng.handle(uid, CHICKEN)
    assert res.intent == "CHAT" and "पूर्ण करायची" not in res.reply


def test_a_real_completion_still_matches_by_words(core_http, uid):
    eng, _, _ = make(core_http)
    add_reminder(core_http, uid, task="चिकन आणायचं", time="09:30")
    res = eng.handle(uid, "चिकन आणलं ते झालं")
    assert res.intent == "COMPLETE_REMINDER"
    assert reminder_status(core_http, uid) == ["done"]


def test_a_real_completion_matches_even_in_conversation(talking, core_http, uid):
    eng, _, _ = talking
    add_reminder(core_http, uid, task="चिकन आणायचं", time="09:30")
    res = eng.handle(uid, "चिकन आणलं झालं")
    assert res.intent == "COMPLETE_REMINDER"
    assert reminder_status(core_http, uid) == ["done"]


def test_a_bare_done_word_outside_conversation_still_completes_the_only_open_reminder(core_http, uid):
    eng, _, _ = make(core_http)
    add_reminder(core_http, uid)
    res = eng.handle(uid, "झालं")
    assert res.intent == "COMPLETE_REMINDER"
    assert reminder_status(core_http, uid) == ["done"]


# ---- evidence 2: a bare "नाही" answering Arjun's own question ----------------------------------------------------
def test_bare_nahi_in_conversation_is_not_a_topic_decline(talking, core_http, uid):
    eng, _, _ = talking
    res = eng.handle(uid, "नाही")
    assert res.intent == "CHAT" and res.mode == "companion"
    assert "नंतर कधीतरी" not in res.reply


def test_bare_ho_in_conversation_is_chat_not_nothing_pending(talking, uid):
    eng, _, _ = talking
    res = eng.handle(uid, "हो")
    assert res.intent == "CHAT" and res.mode == "companion"


def test_bare_nahi_with_no_conversation_is_still_a_decline(core_http, uid):
    eng, _, _ = make(core_http)
    res = eng.handle(uid, "नाही")
    assert res.intent == "DECLINE_TOPIC"


def test_an_explicit_nako_still_ends_the_chat(core_http, uid):
    eng, _, _ = make(core_http, llm=False)
    eng.handle(uid, OPENING)
    assert eng.handle(uid, "नको").intent == "DECLINE_TOPIC"
    assert eng.handle(uid, "डंड").intent == "UNKNOWN"  # and the conversation is over


def test_nahi_right_after_a_saved_reminder_still_undoes_it(talking, core_http, uid):
    eng, _, _ = talking
    eng.handle(uid, "उद्या सकाळी दहा वाजता डॉक्टरकडे जायची आठवण ठेव")
    assert len(core_http.get(f"/users/{uid}/reminders").json()) == 1
    res = eng.handle(uid, "नाही")
    assert "रद्द" in res.reply
    assert core_http.get(f"/users/{uid}/reminders").json() == []


# ---- evidence 3: short or odd utterances --------------------------------------------------------------------------
@pytest.mark.parametrize("said", ["डंड", "गंठलं ते इन्स्पेक्ट करतात", "हॅलो", "आणि मग"])
def test_short_or_odd_turns_stay_in_the_chat(talking, uid, said):
    eng, fake, _ = talking
    before = len(fake.calls)
    res = eng.handle(uid, said)
    assert res.intent == "CHAT" and res.mode == "companion"
    assert "समजलं नाही" not in res.reply
    assert fake.purposes[before:] == ["companion"]  # the intent extractor is not asked mid-conversation


def test_without_a_conversation_the_same_turns_are_still_not_understood(core_http, uid):
    eng, _, _ = make(core_http, llm=False)
    assert eng.handle(uid, "डंड").intent == "UNKNOWN"


def test_rules_only_conversation_uses_the_fixed_companion_lines(core_http, uid):
    eng, _, _ = make(core_http, llm=False)
    eng.handle(uid, OPENING)
    res = eng.handle(uid, "डंड")
    assert res.intent == "CHAT" and "समजलं नाही" not in res.reply


def test_the_conversation_ends_after_five_minutes(core_http, uid):
    eng, _, clock = make(core_http, llm=False)
    eng.handle(uid, OPENING)
    clock.t = 299.0
    assert eng.handle(uid, "डंड").intent == "CHAT"  # still inside the window (and that turn renews it)
    clock.t = 299.0 + 301.0
    assert eng.handle(uid, "डंड").intent == "UNKNOWN"


# ---- what still wins -------------------------------------------------------------------------------------------
def test_emergency_and_distress_win_and_end_the_conversation(core_http, uid):
    eng, _, _ = make(core_http, llm=False)
    eng.handle(uid, OPENING)
    assert eng.handle(uid, "छातीत दुखतंय").intent == "EMERGENCY"
    assert eng.handle(uid, "डंड").intent == "UNKNOWN"  # nothing resumes after a crisis
    eng.handle(uid, OPENING)
    assert eng.handle(uid, "मला मरावंसं वाटतं").intent == "DISTRESS"
    assert eng.handle(uid, "डंड").intent == "UNKNOWN"


def test_care_commands_win_in_conversation(talking, uid):
    eng, _, _ = talking
    assert eng.handle(uid, "आज काय आहे").intent == "LIST_TODAY"
    assert eng.handle(uid, "किती वाजले").intent == "TIME_QUERY"
    res = eng.handle(uid, "उद्या सकाळी दहा वाजता डॉक्टरकडे जायची आठवण ठेव")
    assert res.intent == "CREATE_REMINDER"


def test_an_open_reminder_draft_still_takes_the_next_words(talking, core_http, uid):
    eng, _, _ = talking
    first = eng.handle(uid, "डॉक्टरकडे जायची आठवण ठेव")  # date missing: asks
    assert first.intent == "CREATE_REMINDER" and first.awaiting_confirmation
    assert eng.handle(uid, "डंड").intent == "CREATE_REMINDER"  # still the draft, never the chat


def test_a_medicine_that_is_due_still_wins(talking, core_http, uid):
    eng, _, _ = talking
    core_http.post(
        f"/users/{uid}/medicines",
        json={"name": "Medx (synthetic)", "dose": "1 tablet", "timing": "fixed", "times": ["09:00"]},
    )
    core_http.post("/internal/medicines/tick")
    res = eng.handle(uid, "गोळी घेतली")
    assert res.intent in ("MED_TAKEN", "CONFIRM_YES") or "Medx" in res.reply


# ---- the ask-first mode keeps working ---------------------------------------------------------------------------
def test_ask_first_mode_also_keeps_the_chat_going(core_http, uid):
    eng, _, _ = make(core_http, ask_first=True)
    eng.handle(uid, OPENING)
    res = eng.handle(uid, "नाही")
    assert res.intent == "CHAT"
    assert eng.handle(uid, "डंड").intent == "CHAT"
    add_reminder(core_http, uid)
    assert eng.handle(uid, CHICKEN).intent == "CHAT"
    assert reminder_status(core_http, uid) == ["pending"]


# ---- found by the 23:14 measurement run: a silently kept story must not open the undo window ---------------------
STORY = "माझ्या लहानपणी आम्ही गावाला जायचो तिथे आजीच्या घरी मोठं अंगण होतं आणि आम्ही सगळे भावंडं खेळायचो"


def test_a_bare_nahi_after_a_kept_story_answers_the_chat_and_does_not_delete_the_story(core_http, uid):
    eng, _, _ = make(core_http)
    eng.handle(uid, STORY)  # kept privately, nothing was read back to her
    assert core_http.get(f"/users/{uid}/stories/latest").json() is not None
    res = eng.handle(uid, "नाही")
    assert res.intent == "CHAT" and res.mode == "companion"
    assert core_http.get(f"/users/{uid}/stories/latest").json() is not None  # still there


def test_a_bare_ho_after_a_kept_story_is_chat_not_a_bare_ok(core_http, uid):
    eng, _, _ = make(core_http)
    eng.handle(uid, STORY)
    assert eng.handle(uid, "हो").intent == "CHAT"
