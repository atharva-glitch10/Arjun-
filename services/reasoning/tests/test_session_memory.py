"""Session memory (memory.py + turn.py): EVERY spoken line is in the history the LLM sees; a long silence compresses
instead of deleting; a safety event adds a note instead of wiping; Arjun's open question reaches the LLM."""

import json
from datetime import datetime, timedelta

import httpx
import pytest
from reasoning_svc import memory as mem
from reasoning_svc.core_client import CoreClient
from reasoning_svc.evon import EvonClient, load_intent_schema
from reasoning_svc.turn import TurnEngine

NOW = datetime(2026, 10, 6, 9, 0)
STORY = "आज मी बागेत गेले होते आणि तुळशीला पाणी घातलं"


class Spy:
    """A fake provider that records every request; its reply text is settable."""

    def __init__(self, reply="छान वाटलं ऐकून."):
        self.bodies: list[dict] = []
        self.reply = reply

    def __call__(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        self.bodies.append(body)
        return httpx.Response(200, json={"choices": [{"message": {"content": self.reply}}]})

    @property
    def system(self) -> str:
        return self.bodies[-1]["messages"][0]["content"]

    @property
    def messages(self):
        return [(m["role"], m["content"]) for m in self.bodies[-1]["messages"][1:]]


def make(core_http, **kw):
    spy = Spy()
    client = EvonClient(
        "https://llm.test/v1", "m", http=httpx.Client(transport=httpx.MockTransport(spy)),
        schema=load_intent_schema(), provider="TestAI",
    )
    t = [NOW]
    eng = TurnEngine(
        CoreClient(core_http), client, clock=lambda: t[0], ask_first=False,
        mono=lambda: 1000.0 + (t[0] - NOW).total_seconds(), **kw,
    )
    eng.t = t  # type: ignore[attr-defined]
    return eng, spy


def view(eng, uid):
    return eng.memory.view(uid, eng.clock())


# ---- every kind of turn is recorded ------------------------------------------------------------------------------
def test_a_rule_turn_is_recorded_as_short_text(core_http, uid):
    eng, _ = make(core_http)
    res = eng.handle(uid, "उद्या सकाळी दहा वाजता डॉक्टरकडे जायची आठवण ठेव")
    assert res.intent == "CREATE_REMINDER"
    assert ("assistant", res.reply[:140]) in view(eng, uid).messages


def test_a_safety_turn_is_recorded_with_a_note_and_never_wiped(core_http, uid):
    eng, spy = make(core_http)
    eng.handle(uid, STORY)
    assert eng.handle(uid, "मला छातीत दुखतंय").mode == "safety"
    v = view(eng, uid)
    assert [r for r, _ in v.messages] == ["user", "assistant", "user", "assistant"]
    assert "safety moment" in v.block
    assert eng._convo_at.get(uid) is None  # small talk is paused
    eng.handle(uid, "आता बरं वाटतंय, नातवाबद्दल सांगते")
    assert ("user", STORY) in spy.messages  # the story before the safety moment is still sent


def test_an_action_leaves_a_note_with_the_title_not_her_words(core_http, uid):
    eng, _ = make(core_http)
    eng.memory.event(uid, NOW, "opened for her: ज्ञानेश्वर माऊली")
    assert "What the app did" in view(eng, uid).block and "ज्ञानेश्वर माऊली" in view(eng, uid).block


def test_medicine_wording_never_enters_the_session_as_text(core_http, uid):
    eng, spy = make(core_http)
    eng.handle(uid, STORY)
    eng.handle(uid, "गोळी दुप्पट घेतली तर चालेल का")  # deflected from a template
    eng.handle(uid, "आणि मग मी घरी आले आणि चहा घेतला")
    assert not any("गोळी" in said for _, said in spy.messages)
    assert "What the app did for her" in spy.system and "medicine" in spy.system.split("What the app did for her")[1]


def test_a_line_arjun_said_first_opens_the_history_through_the_system_block(core_http, uid):
    eng, spy = make(core_http)
    eng.memory.arjun_said(uid, NOW, "दुपारचं जेवण झालं का?", "checkin")
    v = view(eng, uid)
    assert v.messages == [] and "दुपारचं जेवण झालं का?" in v.block and "OPEN QUESTION" in v.block
    eng.handle(uid, "हो, वरण भात आणि भाजी खाल्ली")
    assert spy.messages[0][0] == "user"  # providers need the chat to start with her
    assert "दुपारचं जेवण झालं का?" in spy.system


def test_a_spoken_delivery_is_recorded_and_a_released_one_is_not(core_http, uid):
    eng, _ = make(core_http)
    eng._delivered[9] = (uid, "आठवण", "reminder")
    with pytest.raises(Exception):  # noqa: B017 - no such delivery row in core-api; only the bookkeeping matters
        eng.deliver_release(uid, 9, "s1", "interrupted")
    assert 9 not in eng._delivered and view(eng, uid).block == ""


def test_the_exchange_is_recorded_once_with_her_real_words(core_http, uid):
    eng, _ = make(core_http)
    eng.handle(uid, STORY)
    assert [t.text for t in eng.memory.session(uid).turns if t.role == "user"] == [STORY]


# ---- silence compresses, it does not delete ----------------------------------------------------------------------
def test_thirty_one_minutes_of_silence_becomes_a_summary_line(core_http, uid):
    eng, spy = make(core_http)
    eng.handle(uid, STORY)
    eng.t[0] = NOW + timedelta(minutes=31)
    eng.handle(uid, "आता मी स्वयंपाक करते आहे आणि गाणं ऐकते")
    assert len(spy.messages) == 1 and spy.messages[0][0] == "user"
    assert "Raw transcript:" in spy.messages[0][1]
    assert "Earlier in this session" in spy.system and "तुळशीला पाणी घातलं" in spy.system


def test_the_idle_limit_is_a_setting(core_http, uid):
    eng, spy = make(core_http)
    eng.memory.idle = timedelta(minutes=120)
    eng.handle(uid, STORY)
    eng.t[0] = NOW + timedelta(minutes=90)
    eng.handle(uid, "आता मी स्वयंपाक करते आहे आणि गाणं ऐकते")
    assert ("user", STORY) in spy.messages  # still the same conversation


def test_the_summary_is_three_lines_at_most(core_http, uid):
    eng, _ = make(core_http)
    for i in range(6):
        eng.t[0] = NOW + timedelta(hours=i)
        eng.handle(uid, f"आज मी बागेत गेले होते आणि फुलं पाहिली क्रमांक {i}")
    assert 0 < len(eng.memory.session(uid).summary) <= mem.SUMMARY_LINES


def test_twenty_exchanges_are_kept_and_older_ones_are_summarised(core_http, uid):
    eng, spy = make(core_http)
    for i in range(23):
        eng.handle(uid, f"आज मी बागेत गेले होते आणि फुलं पाहिली {i}")
    assert len(spy.messages) == 41  # the 20 newest exchanges plus the new line; nothing beyond is sent as raw turns
    assert eng.memory.session(uid).summary, "older exchanges were compressed, not dropped"
    assert "फुलं पाहिली" in spy.system


def test_the_summary_is_forgotten_after_a_day(core_http, uid):
    eng, spy = make(core_http)
    eng.handle(uid, STORY)
    eng.t[0] = NOW + timedelta(hours=40)
    eng.handle(uid, "नमस्कार अर्जुन, आज काय करायचं")
    assert "Earlier in this session" not in spy.system


# ---- the open question ------------------------------------------------------------------------------------------
def test_a_question_arjun_asked_reaches_the_llm_with_her_short_answer(core_http, uid):
    eng, spy = make(core_http)
    spy.reply = "तुमचं आवडतं भजन कोणतं?"
    eng.handle(uid, "आज मला भजन गावंसं वाटतंय")
    spy.reply = "वा, खूप सुंदर."
    eng.handle(uid, "ज्ञानोबा माऊलींचं")
    assert "OPEN QUESTION" in spy.system and "तुमचं आवडतं भजन कोणतं?" in spy.system
    assert "ANSWER to this question" in spy.system


def test_the_open_question_is_cleared_once_answered(core_http, uid):
    eng, spy = make(core_http)
    spy.reply = "तुमचं आवडतं भजन कोणतं?"
    eng.handle(uid, "आज मला भजन गावंसं वाटतंय")
    spy.reply = "वा, खूप सुंदर."
    eng.handle(uid, "ज्ञानोबा माऊलींचं")
    eng.handle(uid, "आणि मग मी घरी आले")
    assert "OPEN QUESTION" not in spy.system


def test_the_open_question_expires(core_http, uid):
    eng, spy = make(core_http)
    spy.reply = "तुमचं आवडतं भजन कोणतं?"
    eng.handle(uid, "आज मला भजन गावंसं वाटतंय")
    eng.t[0] = NOW + timedelta(minutes=11)
    eng.handle(uid, "ज्ञानोबा माऊलींचं")
    assert "OPEN QUESTION" not in spy.system


def test_questions_asked_today_are_listed_so_they_are_not_repeated(core_http, uid):
    eng, spy = make(core_http)
    spy.reply = "तुमचं आवडतं भजन कोणतं?"
    eng.handle(uid, "आज मला भजन गावंसं वाटतंय")
    spy.reply = "छान."
    eng.handle(uid, "ज्ञानोबा माऊलींचं")
    assert "never ask the same one again" in spy.system and "तुमचं आवडतं भजन कोणतं?" in spy.system


# ---- shaping the reply ------------------------------------------------------------------------------------------
def test_only_the_first_question_is_kept():
    out = mem.shape_questions("छान. तुम्ही काय केलं? कोण आलं होतं?", [], False)
    assert out.count("?") == 1 and "काय केलं?" in out


def test_a_question_is_dropped_when_the_last_reply_was_one_too():
    out = mem.shape_questions("खूप छान वाटलं ऐकून. मग काय झालं?", [], True)
    assert "?" not in out and "छान" in out


def test_a_repeated_question_is_dropped():
    out = mem.shape_questions("छान वाटलं. तुमचं आवडतं भजन कोणतं?", ["तुमचं आवडतं भजन कोणतं?"], False)
    assert "?" not in out


def test_a_reply_that_is_only_a_question_stays():
    assert mem.shape_questions("तुमचं नाव काय?", [], True) == "तुमचं नाव काय?"


def test_the_llm_reply_is_shaped_in_the_turn(core_http, uid):
    eng, spy = make(core_http)
    spy.reply = "छान. तुम्ही काय केलं? कोण आलं होतं?"
    assert eng.handle(uid, STORY).reply.count("?") == 1


# ---- the prompt rules ------------------------------------------------------------------------------------------
def test_the_prompt_asks_for_answers_names_and_at_most_one_question(core_http, uid):
    eng, spy = make(core_http)
    eng.handle(uid, STORY)
    s = spy.system
    assert "ANSWER IT properly" in s and "AT MOST ONE question" in s and "by name and relation" in s
    assert "2-3 simple steps" in s and "व्हिडिओ लावू?" in s  # boundary 10 permits short recipe basics
    assert "Never give medicine advice, doses or a diagnosis" in s and "news facts" in s
    assert "male" in s and "तुम्ही" in s


@pytest.mark.parametrize("text", ["आठवण ठेव", "मी औषध विसरले", "विसरू नको", "उद्या सकाळी आठवण ठेव"])
def test_ordinary_sentences_are_not_memory_commands(text):
    assert mem.parse_remember(text) is None and mem.parse_forget(text) is None


# ---- a reply with one bad sentence is salvaged, not replaced by a fixed line --------------------------------------
def test_one_bad_sentence_is_dropped_and_the_rest_is_kept():
    from reasoning_svc.evon import salvage_companion

    out = salvage_companion("दुपारी ऊन जरा जास्तच असतं. सावलीत बसून थोडा वेळ आराम करा.", "mr")
    assert out == "दुपारी ऊन जरा जास्तच असतं."
    assert salvage_companion("आराम करा.", "mr") is None  # nothing usable left
    assert salvage_companion("छान वाटलं.", "mr") is None  # nothing was wrong: no salvage needed


def test_mentioning_the_doctor_visit_is_not_medical_advice_but_telling_her_to_go_is():
    from reasoning_svc.evon import companion_violations

    assert companion_violations("डॉक्टरकडे जाताना आधार कार्ड आणि जुनी फाईल बरोबर घ्या.", "mr") == []
    assert "medical" in companion_violations("तुम्ही डॉक्टरकडे जा.", "mr")


def test_the_prompt_forbids_guessing_what_she_told_him(core_http, uid):
    eng, spy = make(core_http)
    eng.handle(uid, STORY)
    assert "never guess a preference, a name or an event" in spy.system


def test_a_greeting_after_a_long_silence_may_ask_a_question_again(core_http, uid):
    eng, spy = make(core_http)
    spy.reply = "तुमचं आवडतं भजन कोणतं?"
    eng.handle(uid, "आज मला भजन गावंसं वाटतंय")
    assert eng.memory.previous_reply_was_question(uid, NOW)
    assert not eng.memory.previous_reply_was_question(uid, NOW + timedelta(minutes=45))
