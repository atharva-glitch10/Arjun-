"""Runaway repetition from the speech recognizer (seen live, 2026-10-24 17:15:45).

Prisma wrote the elder's "हो" as `हो हो हो` followed by `कर` 21 times. Every word was a yes-word, but the long
transcript was read as a story and replaced the pending reminder. Repetitions are now collapsed before any
parsing, on every turn, and a pending answer made only of yes-words (or only no-words) counts at any length.
"""

import httpx
import pytest
from reasoning_svc.core_client import CoreClient
from reasoning_svc.evon import EvonClient, load_intent_schema
from reasoning_svc.textutil import collapse_repeats
from reasoning_svc.turn import TurnEngine

DOCTOR = "उद्या सकाळी दहा वाजता डॉक्टरकडे जायचं आहे आठवण कर मला"
REAL_17_15_45 = "हो " * 3 + ("कर " * 21).strip()  # the exact Prisma transcript, by token counts


def test_runs_of_three_or_more_collapse_to_one():
    assert collapse_repeats(REAL_17_15_45) == "हो कर"
    assert collapse_repeats("हो हो हो कर कर कर कर") == "हो कर"
    assert collapse_repeats("नाही नाही नाही") == "नाही"


def test_repeated_phrases_collapse_too():
    assert collapse_repeats("हो कर हो कर हो कर") == "हो कर"
    assert collapse_repeats("ठीक आहे ठीक आहे ठीक आहे ठीक आहे") == "ठीक आहे"


def test_normal_speech_is_left_alone():
    for text in ("हो हो ठेव हो", "नाही नाही", "आज काय आहे", "मी मी म्हणालो", "छान छान वाटलं", DOCTOR, ""):
        assert collapse_repeats(text) == text


def test_punctuation_and_case_do_not_hide_a_repetition():
    assert collapse_repeats("हो, हो, हो, कर.") == "हो, कर."
    assert collapse_repeats("Yes yes YES yes") == "Yes"


def test_the_live_transcript_now_confirms_the_pending_reminder(engine, core_http, uid):
    engine.handle(uid, DOCTOR)
    res = engine.handle(uid, REAL_17_15_45)
    assert res.intent == "CONFIRM_YES" and res.screen == "saved"
    saved = core_http.get(f"/users/{uid}/reminders").json()
    assert [(r["task"], r["due_at"][:16]) for r in saved] == [("डॉक्टरकडे जायचं", "2026-10-07T10:00")]
    assert core_http.get(f"/users/{uid}/memory-book").json() == []  # and no story was offered


@pytest.mark.parametrize("answer", ["हो हो चालेल हो हो ठेव", "होय होय ठेव ठेव हो ठीक बरं हो"])
def test_a_pending_answer_made_only_of_yes_words_is_a_yes_at_any_length(engine, core_http, uid, answer):
    engine.handle(uid, DOCTOR)
    assert engine.handle(uid, answer).intent == "CONFIRM_YES"
    assert len(core_http.get(f"/users/{uid}/reminders").json()) == 1


def test_a_pending_answer_made_only_of_no_words_is_a_no(engine, core_http, uid):
    engine.handle(uid, DOCTOR)
    res = engine.handle(uid, "नाही नको नाही नको नको नाही")
    assert res.intent == "CONFIRM_NO"
    assert core_http.get(f"/users/{uid}/reminders").json() == []
    assert core_http.get(f"/users/{uid}/actions/pending").json() is None


def test_yes_words_mixed_with_other_words_are_not_a_yes(engine, core_http, uid):
    engine.handle(uid, DOCTOR)
    res = engine.handle(uid, "हो पण मला उद्या जमणार नाही बहुतेक")
    assert res.intent != "CONFIRM_YES" and core_http.get(f"/users/{uid}/reminders").json() == []


def test_without_anything_pending_a_long_yes_is_not_a_command(engine, core_http, uid):
    res = engine.handle(uid, "हो हो चालेल हो हो ठेव")
    assert res.intent != "CONFIRM_YES" and core_http.get(f"/users/{uid}/reminders").json() == []


def test_every_turn_is_collapsed_before_the_llm_or_the_rules_see_it(core_http, uid):
    import json
    from datetime import datetime

    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "छान, पुढे काय झालं?"}}]})

    llm = EvonClient("https://llm.test/v1", "m", http=httpx.Client(transport=httpx.MockTransport(handler)),
                     schema=load_intent_schema())
    eng = TurnEngine(CoreClient(core_http), llm, clock=lambda: datetime(2026, 10, 6, 9, 0))
    eng.handle(uid, "छान छान छान छान आज मी बागेत गेलो होतो होतो होतो")
    assert seen[0]["messages"][-1]["content"] == "छान आज मी बागेत गेलो होतो"


def test_a_repetition_cannot_hide_an_emergency(engine, uid):
    res = engine.handle(uid, "छातीत छातीत छातीत दुखतंय दुखतंय दुखतंय")
    assert res.mode == "safety"
