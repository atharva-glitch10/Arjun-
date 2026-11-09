"""Emergency detection for English loanwords and speech-to-text spellings (2026-11-03).

Real failure: the elder said "मला हार्ट अटॅक येतोय"; Sarvam/Prisma wrote it in Devanagari, the lexicon only had Latin
"heart attack", so the LLM chatted instead of the emergency flow. Cases live in
eval/emergency_cases.jsonl (shared with eval/run_eval.py). The lexicon is UNVERIFIED (no native-speaker review).
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from reasoning_svc import distress
from reasoning_svc.core_client import CoreClient
from reasoning_svc.distress import (
    gives_medical_advice,
    has_failsafe_word,
    has_health_word,
    is_emergency,
    mentions_cardiac,
)
from reasoning_svc.evon import EvonClient, load_intent_schema
from reasoning_svc.turn import TurnEngine

ROOT = Path(__file__).resolve().parents[3]
CASES = [json.loads(line) for line in (ROOT / "eval" / "emergency_cases.jsonl").read_text(encoding="utf-8").splitlines() if line]
EMERGENCY = [c["text"] for c in CASES if c["expect"] == "emergency"]
HARMLESS = [c["text"] for c in CASES if c["expect"] == "not_emergency"]
NOW = datetime(2026, 10, 6, 9, 0)


# ---- the rules: 30+ utterances in four kinds, and the harmless ones --------------------------------------------------
def test_the_case_file_has_enough_of_every_kind():
    kinds = {k: sum(1 for c in CASES if c["kind"] == k) for k in ("devanagari", "latin", "mixed", "stt_noisy", "harmless")}
    assert all(n >= 10 for n in kinds.values()), kinds
    assert len(EMERGENCY) >= 30 and len(HARMLESS) >= 10


@pytest.mark.parametrize("text", EMERGENCY)
def test_every_emergency_utterance_is_caught_by_the_rules(text):
    assert is_emergency(text), text


@pytest.mark.parametrize("text", HARMLESS)
def test_harmless_sentences_are_not_an_emergency(text):
    assert not is_emergency(text), text


@pytest.mark.parametrize(
    "text",
    ["HEART  ATTACK", "heart-attack", "Heart, Attack!", "हार्ट   अटॅक", "हार्टअटॅक", "हार्ट अटैक", "हार्ट अटेक", "हार्ट अॅटॅक",
     "हार्ट् अटॅक्", "ह्रदय अटॅक आला", "मला‌ हार्ट अटॅक येतोय"],
)
def test_case_spacing_punctuation_and_spelling_do_not_matter(text):
    assert is_emergency(text) or text == "ह्रदय अटॅक आला", text  # the last one is caught by the "attack + verb" rule below


def test_attack_with_a_verb_is_enough_without_the_word_heart():
    assert is_emergency("ह्रदय अटॅक आला") and is_emergency("attack आला") and is_emergency("अटॅक येतोय")
    assert not is_emergency("attack वाला सिनेमा बघितला")


def test_a_story_about_the_past_is_not_an_emergency_but_a_present_complaint_is():
    assert not is_emergency("माझ्या वडिलांना हार्ट अटॅक आला होता")
    assert not is_emergency("काल छातीत दुखत होतं")
    assert is_emergency("आत्ता छातीत दुखतंय")
    assert is_emergency("पूर्वी हार्ट अटॅक आला होता पण आता पुन्हा येतोय")  # a present marker wins


def test_the_old_lexicon_still_works():
    for t in ("छातीत दुखतंय", "chest pain", "श्वास घेता येत नाही", "heart attack", "बेशुद्ध", "chakkar yete"):
        assert is_emergency(t)


# ---- the whole turn --------------------------------------------------------------------------------------------------
def _resp(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


class Provider:
    """A fake hosted LLM. Tells the safety classifier, the intent reader and the companion apart."""

    def __init__(self, safety=None, companion="छान, सांगा.", safety_error=None):
        self.safety, self.companion, self.safety_error = safety, companion, safety_error
        self.calls: list[str] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        system = body["messages"][0]["content"]
        if "safety classifier" in system:
            self.calls.append("safety")
            if self.safety_error:
                raise self.safety_error
            return _resp(json.dumps(self.safety)) if self.safety is not None else _resp("not json at all")
        if body["temperature"] == 0.0:
            self.calls.append("intent")
            return _resp(json.dumps({"intent": "CHAT", "confidence": 0.9, "language": "mr"}))
        self.calls.append("companion")
        return _resp(self.companion)


def engine_for(core_http, provider=None, **kw):
    if provider is None:
        return TurnEngine(CoreClient(core_http), None, clock=lambda: NOW, **kw)
    http = httpx.Client(transport=httpx.MockTransport(provider))
    client = EvonClient("https://llm.test/v1", "m", http=http, schema=load_intent_schema(), provider="TestAI")
    return TurnEngine(CoreClient(core_http), client, clock=lambda: NOW, **kw)


def test_the_real_failure_now_goes_to_the_emergency_flow_and_alerts_the_family(core_http, uid):
    res = engine_for(core_http).handle(uid, "सर १० १५ मला हार्ट अटॅक येतोय")
    assert res.intent == "EMERGENCY" and res.mode == "safety" and res.screen == "safety"
    assert res.reply == "मी तुमच्या घरच्यांना लगेच कळवलं आहे. जमलं तर 112 ला फोन करा, नाहीतर जवळच्या कोणाला हाक मारा."
    notes = core_http.get(f"/users/{uid}/notifications").json()
    assert [n["kind"] for n in notes] == ["emergency"]  # the dashboard / Telegram alert path, consent or not


def test_the_alert_names_the_son_when_the_family_has_one(core_http, uid):
    core_http.post(f"/users/{uid}/contacts", json={"name": "राहुल", "relation": "मुलगा", "phone": "0000000001"})
    res = engine_for(core_http).handle(uid, "मला हार्ट अटॅक येतोय")
    assert res.reply == "मी राहुलला लगेच कळवलं आहे. जमलं तर 112 ला फोन करा, नाहीतर जवळच्या कोणाला हाक मारा."


@pytest.mark.parametrize("text", [c["text"] for c in CASES if c["expect"] == "emergency"][::4])
def test_a_sample_of_every_kind_reaches_the_emergency_reply_and_never_the_llm(core_http, uid, text):
    provider = Provider()
    res = engine_for(core_http, provider).handle(uid, text)
    assert res.intent == "EMERGENCY" and "112" in res.reply
    assert provider.calls == []  # the rules decided; no chatty LLM reply is even requested


@pytest.mark.parametrize("text", HARMLESS)
def test_harmless_sentences_are_not_taken_for_an_emergency_even_with_the_safety_check(core_http, uid, text):
    provider = Provider(safety={"emergency": False, "distress": False})
    res = engine_for(core_http, provider).handle(uid, text)
    assert res.intent not in ("EMERGENCY", "DISTRESS") and res.mode != "safety"
    assert "112" not in res.reply


# ---- the second layer -------------------------------------------------------------------------------------------------
UNRULED = "माझ्या छातीला काहीतरी वेगळंच होतंय"  # a body word, but no rule matches it
BLOOD_TEST = "उद्या रक्त तपासणी करायची आहे"  # a health word that is not a fail-safe word


def test_the_unruled_sentences_really_are_unruled():
    assert not is_emergency(UNRULED) and has_health_word(UNRULED) and has_failsafe_word(UNRULED)
    assert not is_emergency(BLOOD_TEST) and has_health_word(BLOOD_TEST) and not has_failsafe_word(BLOOD_TEST)


def test_the_llm_check_can_raise_the_alarm(core_http, uid):
    provider = Provider(safety={"emergency": True, "distress": False})
    res = engine_for(core_http, provider).handle(uid, BLOOD_TEST)
    assert res.intent == "EMERGENCY" and provider.calls == ["safety"]
    assert [n["kind"] for n in core_http.get(f"/users/{uid}/notifications").json()] == ["emergency"]


def test_the_llm_check_can_also_find_distress(core_http, uid):
    res = engine_for(core_http, Provider(safety={"emergency": False, "distress": True})).handle(uid, BLOOD_TEST)
    assert res.intent == "DISTRESS"


def test_the_llm_check_saying_all_clear_lets_the_turn_go_on(core_http, uid):
    provider = Provider(safety={"emergency": False, "distress": False})
    res = engine_for(core_http, provider).handle(uid, UNRULED)
    assert res.intent != "EMERGENCY" and provider.calls[0] == "safety"


@pytest.mark.parametrize("failure", ["timeout", "broken_json", "wrong_types", "no_llm", "http_error"])
def test_when_the_llm_check_fails_the_failsafe_words_decide(core_http, uid, failure):
    if failure == "no_llm":
        eng = engine_for(core_http)
    else:
        provider = {
            "timeout": Provider(safety_error=httpx.ReadTimeout("slow")),
            "broken_json": Provider(safety=None),
            "wrong_types": Provider(safety={"emergency": "yes", "distress": 1}),
            "http_error": Provider(safety_error=httpx.ConnectError("down")),
        }[failure]
        eng = engine_for(core_http, provider)
    assert eng.handle(uid, UNRULED).intent == "EMERGENCY"  # छाती is a fail-safe word


def test_a_failed_check_without_a_failsafe_word_does_not_raise_a_false_alarm(core_http, uid):
    res = engine_for(core_http, Provider(safety_error=httpx.ReadTimeout("slow"))).handle(uid, BLOOD_TEST)
    assert res.intent != "EMERGENCY"


@pytest.mark.parametrize("word_text", ["मला attack सारखं वाटतंय", "मला अटॅक सारखं वाटतंय", "छाती जड वाटते आहे", "श्वास कसा तरी होतोय", "माणूस बेशुद्ध झाला"])
def test_the_listed_failsafe_words_are_an_emergency_when_the_check_times_out(core_http, uid, word_text):
    eng = engine_for(core_http, Provider(safety_error=httpx.ReadTimeout("slow")))
    assert eng.handle(uid, word_text).intent == "EMERGENCY"


def test_the_llm_check_is_given_two_seconds_and_a_sentence_without_a_body_word_never_calls_it(core_http, uid):
    seen = {}

    def spy(req):
        if "safety classifier" in json.loads(req.content)["messages"][0]["content"]:
            seen["timeout"] = req.extensions["timeout"]["read"]
        return _resp(json.dumps({"emergency": False, "distress": False}))

    http = httpx.Client(transport=httpx.MockTransport(spy))
    client = EvonClient("https://llm.test/v1", "m", http=http, schema=load_intent_schema(), provider="TestAI")
    TurnEngine(CoreClient(core_http), client, clock=lambda: NOW).handle(uid, BLOOD_TEST)
    assert seen["timeout"] <= 2.0
    provider = Provider()
    engine_for(core_http, provider).handle(uid, "आज हवा छान आहे")
    assert "safety" not in provider.calls


def test_a_complaint_the_symptom_flow_handles_skips_the_extra_llm_call(core_http, uid):
    provider = Provider()
    res = engine_for(core_http, provider).handle(uid, "डोकं दुखतं")
    assert res.intent not in ("EMERGENCY",) and "safety" not in provider.calls


def test_evon_safety_check_returns_none_on_a_timeout_or_garbage():
    def boom(*a, **k):
        raise httpx.ReadTimeout("slow")

    client = EvonClient("https://llm.test/v1", "m", http=httpx.Client(transport=httpx.MockTransport(lambda r: _resp("x"))),
                        schema=load_intent_schema(), provider="TestAI")
    assert client.safety_check("छाती", timeout=2.0) is None  # "x" is not JSON
    client._chat = boom  # type: ignore[method-assign]
    assert client.safety_check("छाती", timeout=2.0) is None


# ---- the LLM never answers a heart attack ------------------------------------------------------------------------------
ADVICE = "हार्ट अटॅक असेल तर एस्प्रिन घ्या आणि शांत झोपा."


def test_advice_detection():
    assert gives_medical_advice(ADVICE) and gives_medical_advice("Take an aspirin and lie down")
    assert not gives_medical_advice("छान, सांगा.")
    assert mentions_cardiac("हार्ट अटॅक") and not mentions_cardiac("आज हवा छान आहे")


def test_an_llm_reply_with_cardiac_advice_to_her_cardiac_words_becomes_the_emergency_flow(core_http, uid):
    provider = Provider(safety={"emergency": False, "distress": False}, companion=ADVICE)
    res = engine_for(core_http, provider).handle(uid, "माझ्या वडिलांना हार्ट अटॅक आला होता")
    assert res.intent == "EMERGENCY" and res.mode == "safety" and "112" in res.reply
    assert "एस्प्रिन" not in res.reply and "झोपा" not in res.reply
    assert "emergency" in [n["kind"] for n in core_http.get(f"/users/{uid}/notifications").json()]


def test_a_reply_that_mentions_a_heart_attack_with_advice_unprompted_becomes_the_doctor_line(core_http, uid):
    from reasoning_svc.turn import TurnResult

    eng = engine_for(core_http)
    llm_reply = TurnResult("हार्ट अटॅक टाळायचा असेल तर रोज गोळी घ्या.", "CHAT", "companion", "mr", source="llm")
    res = eng._guard_cardiac_reply(uid, "आज बागेत छान वाटलं", llm_reply, "mr", {}, 0.0)
    assert res is not None and res.intent == "MEDICAL_QUESTION" and "गोळी" not in res.reply
    assert [n["kind"] for n in core_http.get(f"/users/{uid}/notifications").json()] == []  # no false family alarm
    # a fixed template (source "rules", care mode) is never rewritten
    fixed = TurnResult("हार्ट अटॅक असेल तर 112 वर फोन करा, गोळी नको.", "EMERGENCY", "care", "mr", source="rules")
    assert eng._guard_cardiac_reply(uid, "x", fixed, "mr", {}, 0.0) is None


def test_an_ordinary_llm_reply_is_not_touched(core_http, uid):
    provider = Provider(companion="छान वाटलं असेल. तुम्ही काय पाहिलं?")
    res = engine_for(core_http, provider).handle(uid, "आज बागेत छान वाटलं आणि फुलं पाहिली")
    assert res.reply == "छान वाटलं असेल. तुम्ही काय पाहिलं?"


# ---- the voice agent's copy must agree --------------------------------------------------------------------------------
def test_the_voice_agents_local_safety_words_let_every_emergency_through():
    sys.path.insert(0, str(ROOT / "services" / "voice-agent"))
    try:
        import importlib

        safety_words = importlib.import_module("safety_words")
        assert [t for t in EMERGENCY if not safety_words.is_safety_phrase(t)] == []
        assert not any(safety_words.is_safety_phrase(t) for t in HARMLESS if not has_failsafe_word(t) and not is_emergency(t))
    finally:
        sys.path.remove(str(ROOT / "services" / "voice-agent"))


def test_the_module_exports_what_turn_py_imports():
    for name in ("loanword_emergency", "has_health_word", "has_failsafe_word", "gives_medical_advice", "mentions_cardiac"):
        assert hasattr(distress, name)
