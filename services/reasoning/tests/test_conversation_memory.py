"""Conversation memory (task B): the LLM sees this whole conversation, care turns included as short text."""

import json
from datetime import datetime, timedelta

import httpx
from reasoning_svc import config
from reasoning_svc.core_client import CoreClient
from reasoning_svc.evon import EvonClient, load_intent_schema
from reasoning_svc.turn import TurnEngine

NOW = datetime(2026, 10, 6, 9, 0)
OPENING = "आज मी बागेत गेले होते आणि मला खूप छान वाटलं"


class Llm:
    def __init__(self):
        self.bodies: list[dict] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        self.bodies.append(body)
        return httpx.Response(200, json={"choices": [{"message": {"content": "छान. मग काय झालं?"}}]})


def make(core_http, **kw):
    llm = Llm()
    client = EvonClient(
        "https://llm.test/v1", "m", http=httpx.Client(transport=httpx.MockTransport(llm)),
        schema=load_intent_schema(), provider="TestAI",
    )
    clock = kw.pop("clock", lambda: NOW)
    return TurnEngine(CoreClient(core_http), client, clock=clock, ask_first=False, **kw), llm


def sent(llm):
    """(role, text) of the last companion request, without the system prompt and the new user turn."""
    msgs = llm.bodies[-1]["messages"]
    return [(m["role"], m["content"]) for m in msgs[1:-1]]


def test_the_default_history_is_eight_exchanges():
    assert config.llm_settings({}).history_exchanges == 8
    assert config.LLM_HISTORY_EXCHANGES == 8


def test_a_care_turn_in_the_conversation_is_in_the_history_as_short_text(core_http, uid):
    eng, llm = make(core_http)
    eng.handle(uid, OPENING)
    care = eng.handle(uid, "उद्या सकाळी दहा वाजता डॉक्टरकडे जायची आठवण ठेव")
    assert care.intent == "CREATE_REMINDER"
    eng.handle(uid, "आणि मग मी घरी आले आणि चहा घेतला")
    turns = sent(llm)
    assert ("user", "उद्या सकाळी दहा वाजता डॉक्टरकडे जायची आठवण ठेव") in turns
    assert ("assistant", care.reply[:140]) in turns
    assert all(len(said) <= 300 for _, said in turns)


def test_a_long_care_turn_is_cut_short(core_http, uid):
    eng, llm = make(core_http)
    eng.handle(uid, OPENING)
    eng.handle(uid, "आज काय आहे " + "x" * 400)
    eng.handle(uid, "आणि मग मी घरी आले आणि चहा घेतला")
    assert all(len(said) <= 140 for role, said in sent(llm)[2:4])


def test_medicine_turns_never_enter_the_llm_history(core_http, uid):
    eng, llm = make(core_http)
    eng.handle(uid, OPENING)
    eng.handle(uid, "गोळी दुप्पट घेतली तर चालेल का")  # a medicine question: deflected from a template
    eng.handle(uid, "आणि मग मी घरी आले आणि चहा घेतला")
    assert not any("गोळी" in said for _, said in sent(llm))


def test_only_the_last_eight_exchanges_are_sent_by_default(core_http, uid):
    eng, llm = make(core_http, history_exchanges=config.llm_settings({}).history_exchanges)
    for i in range(12):
        eng.handle(uid, f"आज मी बागेत गेले होते आणि फुलं पाहिली {i}")
    assert len(sent(llm)) == 16


def test_a_thirty_minute_silence_starts_a_new_conversation(core_http, uid):
    t = [NOW]
    eng, llm = make(core_http, clock=lambda: t[0])
    eng.handle(uid, OPENING)
    t[0] = NOW + timedelta(minutes=31)
    eng.handle(uid, "आता मी स्वयंपाक करते आहे आणि गाणं ऐकते")
    assert sent(llm) == []


def test_distress_drops_the_history(core_http, uid):
    eng, llm = make(core_http)
    eng.handle(uid, OPENING)
    assert eng.handle(uid, "मला मरावंसं वाटतं").intent == "DISTRESS"
    eng.handle(uid, "आता मी स्वयंपाक करते आहे आणि गाणं ऐकते")
    assert sent(llm) == []
