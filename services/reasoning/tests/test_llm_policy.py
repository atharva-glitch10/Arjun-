"""LLM-first understanding: one call per non-safety turn, the rule fallback, and what the companion may say.

Boundaries: 1 (the LLM never touches the DB), 4-6 (AI, no medical advice, medicines), 8 (safety first),
9 (no engagement tricks), 10 (recipe basics allowed, health and news facts forbidden). Evon is not involved.
"""

import json
from datetime import datetime

import httpx
import pytest
from reasoning_svc import replies as rp
from reasoning_svc.core_client import CoreClient
from reasoning_svc.evon import EvonClient, load_intent_schema, sanitize_companion
from reasoning_svc.turn import TurnEngine

NOW = datetime(2026, 10, 6, 9, 0)
DOCTOR = "उद्या सकाळी दहा वाजता डॉक्टरकडे जायचं आहे आठवण कर मला"
STORY = "आज मी बागेत फिरायला गेलो होतो खूप छान वाटलं"
GOOD = "छान वाटलं असेल. त्या बागेत तुम्ही काय पाहिलं?"


def _resp(content, finish=None):
    choice = {"message": {"content": content}}
    if finish:
        choice["finish_reason"] = finish
    return httpx.Response(200, json={"choices": [choice]})


def _payload(reply=GOOD, intent="chat", confidence=0.9, **slots):
    return {
        "intent": intent,
        "slots": {"task": None, "date": None, "time": None, "time_ambiguous": False, "query": None,
                  "media_kind": None, "media_specific": False, "control": None, "contact": None,
                  "confirm": None, "choice": None, "checkin_answer": None, "bp": None, **slots},
        "reply": reply,
        "confidence": confidence,
    }


class Llm:
    """A fake provider that records every request and separates the one understand call from safety."""

    def __init__(self, payload=None, companion=GOOD, finish=None, error=None):
        self.calls: list[dict] = []
        self.payload = payload if payload is not None else _payload()
        self.companion = companion
        self.finish = finish
        self.error = error

    def __call__(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        system = body["messages"][0]["content"]
        if "Return ONLY one JSON object" in system:
            purpose = "understand"
        elif "safety classifier" in system:
            purpose = "safety"
        elif "check-in question" in system:
            purpose = "checkin"
        else:
            purpose = "companion"
        body["_purpose"] = purpose
        body["_timeout"] = req.extensions["timeout"]["read"]
        self.calls.append(body)
        if self.error is not None:
            raise self.error
        if purpose == "understand":
            return _resp(json.dumps(self.payload), self.finish)
        if purpose == "safety":
            return _resp(json.dumps({"emergency": False, "distress": False}))
        return _resp(self.companion)

    @property
    def purposes(self):
        return [c["_purpose"] for c in self.calls]

    @property
    def last(self):
        return self.calls[-1]


def make_engine(core_http, llm, **kw):
    http = httpx.Client(transport=httpx.MockTransport(llm))
    client = EvonClient("https://llm.test/v1", "m", http=http, schema=load_intent_schema(), provider="TestAI")
    return TurnEngine(CoreClient(core_http), client, clock=lambda: NOW, **kw)


# ---- when it is called -----------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        DOCTOR,
        "आज काय आहे",
        "उद्या काय आहे",
        "kiti vajle",
        "मदत",
        "हॅलो",
        "ऐकू येतंय का",
        "हो",
        "नको",
        "मी तुला सांगितलं ते विसर",
    ],
)
def test_every_non_safety_turn_makes_exactly_one_understanding_call(core_http, uid, text):
    llm = Llm()
    make_engine(core_http, llm).handle(uid, text)
    assert llm.purposes == ["understand"], text


@pytest.mark.parametrize("text", ["मला छातीत दुखतंय", "mala jagaychi iccha nahi"])
def test_emergency_and_distress_run_before_and_without_any_llm_call(core_http, uid, text):
    llm = Llm(error=AssertionError("safety must not call the LLM"))
    res = make_engine(core_http, llm).handle(uid, text)
    assert res.mode == "safety" and llm.calls == []


def test_a_story_that_mentions_medicine_stays_chat(core_http, uid):
    # The old keyword parser took the medicine word and recorded a dose; the whole sentence is chat.
    llm = Llm(payload=_payload(reply="बरं वाटलं असेल. बागेत काय पाहिलं?"))
    res = make_engine(core_http, llm).handle(uid, "आज मी औषध घेतलं आणि बागेत फिरायला गेलो, खूप छान वाटलं")
    assert res.intent == "CHAT" and res.reply == "वाटलं असेल. बागेत काय पाहिलं?"
    assert llm.purposes.count("understand") == 1


# ---- each intent does the right thing --------------------------------------------------------------
def test_llm_reminder_add_becomes_a_pending_reminder(core_http, uid):
    llm = Llm(payload=_payload(intent="reminder_add", task="doctor", date="2026-10-07", time="10:00"))
    res = make_engine(core_http, llm).handle(uid, "udya doctor")
    assert res.source == "llm" and res.awaiting_confirmation and res.screen == "confirm"
    assert core_http.get(f"/users/{uid}/reminders").json() == []
    assert core_http.get(f"/users/{uid}/actions/pending").json()["payload"]["time"] == "10:00"


@pytest.mark.parametrize(
    "intent,slots,expected",
    [
        ("medicine_taken", {}, "MED_TAKEN"),
        ("medicine_query", {}, "MEDICAL_QUESTION"),
        ("news", {}, "NEWS_READ"),
        ("today_query", {}, "LIST_TODAY"),
        ("media", {"media_kind": "unknown"}, "OPEN_MEDIA"),
        ("call_family", {}, "CALL_FAMILY_REMINDER"),
        ("message_family", {}, "REQUEST_CAREGIVER"),
        ("stop", {"control": "stop"}, "MEDIA_CONTROL"),
        ("undo", {}, "DECLINE_TOPIC"),  # nothing was just done, so "undo" is a topic decline
        ("health_complaint", {}, "SYMPTOM"),
        ("chat", {}, "CHAT"),
        ("unclear", {}, "UNKNOWN"),
    ],
)
def test_each_llm_intent_reaches_its_action(core_http, uid, intent, slots, expected):
    llm = Llm(payload=_payload(intent=intent, **slots))
    res = make_engine(core_http, llm).handle(uid, "हं")
    assert res.intent == expected
    assert llm.purposes == ["understand"]


def test_a_long_sentence_is_not_a_no_to_an_action_that_was_already_done(core_http, uid):
    # Companion-eval regression: after "राहुलला सांग मला फोन कर", "माझा चस्मा सापडत नाही" was read as "नाही",
    # undid the family message and said "घरच्यांना कळवलं की आता मदत नको". A longer sentence is not an undo.
    llm = Llm(payload=_payload(intent="message_family"))
    eng = make_engine(core_http, llm, ask_first=False)
    first = eng.handle(uid, "राहुलला सांग मला फोन कर")
    assert first.intent == "REQUEST_CAREGIVER" and not first.awaiting_confirmation

    llm.payload = _payload(intent="chat", reply="चस्मा कुठे ठेवला होता? मी शोधायला मदत करतो.")
    res = eng.handle(uid, "माझा चस्मा सापडत नाही")
    assert res.intent == "CHAT"
    assert res.reply.startswith("चस्मा कुठे")
    assert "मदत नको" not in res.reply


def test_a_health_complaint_is_not_a_no_to_an_open_question(core_http, uid):
    # Regression from the companion eval: "आज माझी तब्येत बरी नाही" ended in "नाही", so the rule parser read
    # it as a no, cancelled the pending reminder, and said the family was told help is not needed.
    eng = make_engine(core_http, Llm(payload=_payload(intent="reminder_add", task="doctor",
                                                     date="2026-10-07", time="10:00")))
    eng.handle(uid, DOCTOR)
    assert core_http.get(f"/users/{uid}/actions/pending").json() is not None

    llm = Llm(payload=_payload(intent="health_complaint"))
    res = make_engine(core_http, llm).handle(uid, "आज माझी तब्येत बरी नाही")
    assert res.intent == "SYMPTOM" and res.mode == "companion"
    assert "मदत नको" not in res.reply
    assert core_http.get(f"/users/{uid}/actions/pending").json() is not None  # still open, asked again later
    assert llm.purposes == ["understand"]


# ---- the rules are the fallback, and every fallback says why ----------------------------------------
def test_a_timeout_falls_back_to_the_rules_and_logs_the_reason(core_http, uid):
    llm = Llm(error=httpx.ReadTimeout("slow"))
    res = make_engine(core_http, llm).handle(uid, STORY)
    assert res.source != "llm" and bool(res.reply)
    assert res.trace["route"] == "rules" and res.trace["route_reason"] == "timeout_retry"


def test_invalid_json_falls_back_without_a_second_intent_call(core_http, uid):
    class Bad(Llm):
        def __call__(self, req):
            body = json.loads(req.content)
            self.calls.append({**body, "_purpose": "understand"})
            return _resp("{not json")  # look like JSON, fail to parse: not the accepted plain-prose path

    llm = Bad()
    res = make_engine(core_http, llm).handle(uid, "udya doctor")
    understands = [c for c in llm.calls if "response_format" in c]
    assert len(understands) == 1  # no legacy extract_intent call after the unified call failed
    assert res.trace["route_reason"] == "invalid_json"


def test_a_low_confidence_action_intent_is_ignored(core_http, uid):
    llm = Llm(payload=_payload(intent="reminder_add", confidence=0.2, task="doctor", date="2026-10-07",
                               time="10:00"))
    res = make_engine(core_http, llm).handle(uid, "udya doctor")
    assert res.trace["route_reason"] == "low_confidence"
    assert core_http.get(f"/users/{uid}/actions/pending").json() is None


def test_no_budget_means_no_call(core_http, uid):
    llm = Llm()
    res = make_engine(core_http, llm, llm_timeout_s=0.1).handle(uid, STORY)
    assert llm.calls == [] and res.trace["route"] == "rules" and res.trace["route_reason"] == "no_budget"


def test_understanding_timeout_retries_once_with_six_recent_turns(core_http, uid):
    class TimeoutOnce:
        def __init__(self):
            self.calls = []

        def __call__(self, req):
            body = json.loads(req.content)
            self.calls.append(body)
            if len(self.calls) == 1:
                raise httpx.ReadTimeout("synthetic timeout", request=req)
            return _resp(json.dumps(_payload()))

    provider = TimeoutOnce()
    engine = make_engine(core_http, provider)
    user = engine.core.user(uid)
    engine._llm_deadline = engine._mono() + 6
    data, reason, attempted = engine._understand(uid, "आज बागेत फुलं आली", "mr", NOW, user)
    assert attempted and reason == "ok" and data is not None
    assert len(provider.calls) == 2
    assert provider.calls[0]["messages"][0]["content"] == provider.calls[1]["messages"][0]["content"]
    assert provider.calls[1]["messages"][-1]["content"].endswith("आज बागेत फुलं आली")


def test_a_slow_or_failing_provider_falls_back_to_the_fixed_line(core_http, uid):
    def boom(req):
        raise httpx.ReadTimeout("slow", request=req)

    http = httpx.Client(transport=httpx.MockTransport(boom))
    client = EvonClient("https://llm.test/v1", "m", http=http, schema=load_intent_schema())
    eng = TurnEngine(CoreClient(core_http), client, clock=lambda: NOW)
    res = eng.handle(uid, STORY)
    assert res.source != "llm" and bool(res.reply)


def test_a_bad_intent_name_is_rejected(core_http, uid):
    llm = Llm(payload=_payload(intent="DROP_TABLE"))
    res = make_engine(core_http, llm).handle(uid, "udya doctor")
    assert res.trace["route_reason"] == "bad_intent"


# ---- context and prompt -----------------------------------------------------------------------------
def test_the_prompt_carries_context_masculine_forms_and_no_banned_lines(core_http, uid):
    core_http.post(f"/users/{uid}/contacts", json={"name": "Rahul", "relation": "son", "phone": "0000000000"})
    llm = Llm()
    make_engine(core_http, llm).handle(uid, STORY)
    system = llm.last["messages"][0]["content"]
    for needle in ("USER CONTEXT", "Aaji", "Rahul", "son", "Today:", "NEVER ACT DUMB",
                   "ALWAYS TRY TO GIVE A SOLUTION", "सांगतो", "विचारतो", "करतो", "तुम्ही",
                   "1-2 short sentences", "Never say you missed her"):
        assert needle in system, needle
    for banned in ("आता कसं वाटतंय?", "हे अजून मला जमत नाही", "at most 12 words", "मला वाटतं"):
        assert banned not in system
    assert "0000000000" not in system  # family names and relations, never numbers


def test_only_the_last_four_exchanges_are_sent(core_http, uid):
    llm = Llm()
    eng = make_engine(core_http, llm, history_exchanges=4)
    for i in range(7):
        eng.handle(uid, f"{STORY} {i}")
    last = llm.last["messages"]
    assert [m["role"] for m in last] == ["system"] + ["user", "assistant"] * 4 + ["user"]
    assert last[1]["content"].endswith(" 2")  # exchanges 0-2 were dropped
    assert llm.last["max_tokens"] == 250
    assert llm.last["temperature"] == 0.5


def test_finish_reason_length_cuts_the_reply_to_its_last_full_sentence(core_http, uid):
    llm = Llm(payload=_payload(reply="एक छान वाक्य. अर्धवट"), finish="length")
    res = make_engine(core_http, llm).handle(uid, STORY)
    assert res.reply == "एक छान वाक्य."


# ---- what it may say ---------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bad,reason",
    [
        ("मी माणूस आहे, मला पण भूक लागली.", "human"),
        ("I am a real person like you.", "human"),
        ("रोज सकाळी 500 mg ची गोळी घ्या.", "medical"),
        ("तुम्ही हे औषध घ्या आणि बरं वाटेल.", "medical"),
        ("That sounds nice, tell me more.", "script"),
        ("एक. दोन. तीन. चार. पाच.", "sentences"),
    ],
)
def test_replies_that_break_a_narrow_boundary_are_rejected(bad, reason):
    text, reasons = sanitize_companion(bad, "mr")
    assert text is None and reason in reasons


def test_missed_you_and_a_recipe_fact_are_the_prompts_job_not_the_sanitizer():
    # The sanitizer was narrowed on 2026-11-04: it must not throw away a useful answer for these.
    assert sanitize_companion("मला तुमची खूप आठवण आली.", "mr")[0] is not None
    assert sanitize_companion("भारताची राजधानी दिल्ली आहे.", "mr")[0] is not None


def test_recipe_question_gets_a_useful_answer_but_health_advice_stays_blocked(core_http, uid):
    llm = Llm(payload=_payload(reply="पुरणपोळीला कणीक भिजवून सारण भरा. पोळ्या तव्यावर भाजा. व्हिडिओ लावू?"))
    reply = make_engine(core_http, llm).handle(uid, "पुरणपोळी कशी करतात?").reply
    assert "सारण" in reply and "व्हिडिओ लावू?" in reply
    assert sanitize_companion("रोज औषध घ्या.", "mr")[0] is None
    prompt = llm.calls[0]["messages"][0]["content"]
    assert "2-3 simple steps" in prompt and "news facts" in prompt


def test_agreeing_with_her_rest_plan_is_allowed_and_leading_fillers_are_stripped():
    assert sanitize_companion("हो, आराम करा, नंतर बोलूया.", "mr", "आता आराम करते") == (
        "हो, आराम करा, नंतर बोलूया.", []
    )
    assert sanitize_companion("का, अहो, छान वाटलं.", "mr")[0] == "छान वाटलं."
    assert sanitize_companion("हो, आराम करा आणि पाणी प्या.", "mr", "आता थोडा आराम करते") == (
        "हो, आराम करा, नंतर बोलूया.", []
    )


def test_d11_rest_plan_is_not_replaced_by_the_fixed_fallback(core_http, uid):
    llm = Llm(payload=_payload(reply="हो, आराम करा, नंतर बोलूया."))
    result = make_engine(core_http, llm).handle(uid, "आता थोडा आराम करते")
    assert result.reply == "हो, आराम करा, नंतर बोलूया."


def test_llm_user_context_contains_address_as_and_forbids_invented_tai(core_http, uid):
    core_http.patch(f"/users/{uid}", json={"address_as": "आजी"})
    llm = Llm()
    make_engine(core_http, llm).handle(uid, STORY)
    prompt = llm.calls[0]["messages"][0]["content"]
    assert "address her as आजी" in prompt and "never call her ताई" in prompt


def test_a_rejected_llm_reply_is_retried_once_then_replaced(core_http, uid):
    calls = {"companion": 0}

    def handler(req):
        body = json.loads(req.content)
        system = body["messages"][0]["content"]
        if "Return ONLY one JSON object" in system:
            return _resp(json.dumps(_payload(reply="मी माणूस आहे, मला तुमची आठवण आली.")))
        calls["companion"] += 1
        return _resp(GOOD)

    client = EvonClient("https://llm.test/v1", "m", http=httpx.Client(transport=httpx.MockTransport(handler)),
                        schema=load_intent_schema(), provider="TestAI")
    res = TurnEngine(CoreClient(core_http), client, clock=lambda: NOW).handle(uid, STORY)
    assert res.reply == GOOD and res.source == "llm"
    assert calls["companion"] == 1  # exactly one corrective retry


def test_a_reply_that_stays_bad_gets_a_topic_specific_clarification(core_http, uid):
    llm = Llm(payload=_payload(reply="मी माणूस आहे, मला तुमची आठवण आली."), companion="I am a real person.")
    res = make_engine(core_http, llm).handle(uid, STORY)
    assert res.reply and res.reply not in rp.CHAT["mr"]
    assert llm.purposes.count("companion") == 1  # one retry, not a loop


def test_a_good_reply_passes_and_more_than_four_sentences_is_rejected():
    assert sanitize_companion(GOOD, "mr") == (GOOD, [])
    long = "छान वाटलं. बाग सुंदर असेल. मग पुढे काय झालं? तिथे कोण होतं? आणि नंतर?"
    text, reasons = sanitize_companion(long, "mr")
    assert text is None and reasons == ["sentences"]
    four = "छान वाटलं. बाग सुंदर असेल. मग पुढे काय झालं? तिथे कोण होतं?"
    assert sanitize_companion(four, "mr") == (four, [])
