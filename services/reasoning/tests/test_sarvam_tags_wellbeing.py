"""Sarvam-105B config, thinking removal, runtime voice tags, LLM limits, the family summary, /turn rate limit."""

import json
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from reasoning_svc import main as main_mod
from reasoning_svc.config import llm_settings
from reasoning_svc.core_client import CoreClient
from reasoning_svc.evon import EvonClient, Limiter, LlmBusy, split_voice_tags, strip_thinking
from reasoning_svc.ratelimit import TokenBucket
from reasoning_svc.turn import TurnEngine
from reasoning_svc.wellbeing import Conversation, Tracker

NOW = datetime(2026, 10, 6, 9, 0)


# ---- Sarvam config -------------------------------------------------------------------------------------------
def test_sarvam_key_alone_turns_on_sarvam_105b_without_thinking():
    s = llm_settings({"SARVAM_API_KEY": "sk-secret-123"})
    assert s.configured and s.provider == "sarvam" and s.model == "sarvam-105b"
    assert s.base_url == "https://api.sarvam.ai/v1"
    assert s.reasoning_off and not s.send_template_kwargs
    assert "sk-secret-123" not in repr(s)  # the key is never printed


def test_explicit_llm_settings_still_win_and_thinking_can_be_kept():
    s = llm_settings({"LLM_BASE_URL": "https://api.sarvam.ai/v1", "LLM_MODEL": "sarvam-105b-conversations",
                      "LLM_API_KEY": "k", "LLM_REASONING": "1", "SARVAM_API_KEY": "other"})
    assert s.model == "sarvam-105b-conversations" and not s.reasoning_off
    assert not llm_settings({}).configured


def _client(handler, **kw):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return EvonClient("https://api.sarvam.ai/v1", "sarvam-105b", http=http, schema={}, provider="sarvam",
                      send_template_kwargs=False, reasoning_off=True, **kw)


def test_request_body_disables_reasoning_and_answer_comes_back_without_think():
    sent = {}

    def handler(req: httpx.Request) -> httpx.Response:
        sent.update(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "<think>plan</think>छान! <laugh> मग?"}}]})

    out = _client(handler).companion_reply("मी आज बाग केली", "mr")
    assert sent["reasoning_effort"] is None and "chat_template_kwargs" not in sent
    assert out == "छान! <laugh> मग?"
    assert "voice tag" in sent["messages"][0]["content"]  # the LLM is told it may choose a tag


def test_thinking_only_or_unclosed_is_no_answer():
    assert strip_thinking("<think>a</think>  ") is None
    assert strip_thinking("<think>never closed") is None
    assert strip_thinking("नमस्कार</think>") == "नमस्कार"


def test_voice_tags_only_allowed_ones_at_most_two_exact_spelling():
    clean, voice = split_voice_tags("<SIGH> खरं आहे. <shouting> अरे! <slow> हळू <laugh>")
    assert clean == "खरं आहे. अरे! हळू"
    assert voice == "<sigh> खरं आहे. अरे! <slow> हळू"


# ---- concurrency / rate limit / backoff ----------------------------------------------------------------------
def test_limiter_never_queues():
    t = [0.0]
    lim = Limiter(max_concurrent=1, per_minute=2, clock=lambda: t[0])
    lim.acquire()
    with pytest.raises(LlmBusy):
        lim.acquire()  # one in flight already
    lim.release()
    lim.acquire()
    lim.release()
    with pytest.raises(LlmBusy):
        lim.acquire()  # 2 per minute used
    t[0] = 61.0
    lim.acquire()
    lim.release()
    lim.cool_down(30)
    with pytest.raises(LlmBusy):
        lim.acquire()


def test_a_provider_429_backs_off_and_the_rules_answer():
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(429, headers={"retry-after": "20"})

    c = _client(handler)
    assert c.companion_reply("नमस्कार", "mr") is None
    assert c.companion_reply("नमस्कार", "mr") is None
    assert len(calls) == 1  # the second call was not sent at all


def test_companion_speech_carries_the_tag_but_the_screen_does_not(core_http, uid):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "<laugh> वा, छान! मग काय झालं?"}}]})

    eng = TurnEngine(CoreClient(core_http), _client(handler), clock=lambda: NOW, ask_first=False)
    res = eng.handle(uid, "आज मी नातवासोबत खूप गप्पा मारल्या आणि आम्ही बागेत फिरायला गेलो होतो")
    assert res.reply == "छान! मग काय झालं?"  # the leading filler "वा" is stripped from screen and voice
    assert res.speech == "<laugh> छान! मग काय झालं?"


# ---- family summary ------------------------------------------------------------------------------------------
def _conv(*intents):
    c = Conversation(started=NOW, last=NOW)
    c.intents = list(intents)
    c.turns = [("user", "x"), ("assistant", "y")] * len(intents)
    return c


def test_without_consent_feelings_stay_private_but_help_and_emergency_show():
    t = Tracker(core=None, llm=None)  # type: ignore[arg-type]
    row = t.entry(_conv("CHAT", "LONELY", "CREATE_REMINDER"), consent=False)
    assert row["severity"] == "normal" and row["mood"] == "not_assessed"
    assert "lonely" not in row["summary"] and "set a reminder" in row["summary"]
    assert t.entry(_conv("EMERGENCY"), consent=False)["severity"] == "emergency"
    assert t.entry(_conv("REQUEST_CAREGIVER"), consent=False)["severity"] == "urgent"


def test_with_consent_mood_and_level_show_and_the_llm_can_raise_never_lower():
    class FakeLlm:
        def __init__(self, level):
            self.level = level

        def summarize_conversation(self, turns, language):
            return {"summary": "Talked about her garden; said her knee hurts.", "mood": "worried",
                    "severity": self.level, "topics": ["garden"]}

    low = Tracker(core=None, llm=FakeLlm("normal")).entry(_conv("LONELY"), consent=True)  # type: ignore[arg-type]
    assert low["severity"] == "watch" and low["source"] == "llm" and low["mood"] == "worried"
    high = Tracker(core=None, llm=FakeLlm("urgent")).entry(_conv("CHAT"), consent=True)  # type: ignore[arg-type]
    assert high["severity"] == "urgent"


def test_conversations_flush_after_silence_into_core_api(core_http, uid):
    clock = [NOW]
    tr = Tracker(CoreClient(core_http), None, clock=lambda: clock[0], idle_s=180)
    tr.record(uid, "आज काय आहे", "आज तुमच्याकडे काही नाही", "LIST_TODAY")
    assert tr.flush_idle() == 0
    clock[0] = NOW + timedelta(minutes=4)
    assert tr.flush_idle() == 1
    rows = core_http.get(f"/users/{uid}/wellbeing").json()
    assert rows and rows[0]["summary"].startswith("Talked with Arjun (1 turn)")
    assert "आज काय आहे" not in rows[0]["summary"]  # never her words


def test_summary_prompt_forbids_quotes_and_diagnosis():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(json.loads(req.content))
        body = {"summary": "She talked about cooking.\nShe sounded cheerful.", "mood": "happy", "severity": "normal", "topics": ["food"]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(body)}}]})

    got = _client(handler).summarize_conversation([("user", "मी पुरणपोळी केली")], "mr")
    assert got == {"summary": "She talked about cooking.\nShe sounded cheerful.", "mood": "happy", "severity": "normal", "topics": ["food"]}
    prompt = seen["messages"][0]["content"]
    assert "never quote" in prompt and "never diagnose" in prompt and "2-3 brief lines" in prompt


def test_summary_rejects_quoted_single_line_and_tracker_uses_rules_fallback():
    client = _client(lambda req: httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(
        {"summary": 'She said "hello".', "mood": "happy", "severity": "normal", "topics": []})}}]}))
    assert client.summarize_conversation([("user", "hello")], "en") is None

    class Broken:
        def summarize_conversation(self, turns, language):
            raise httpx.TimeoutException("timeout")

    row = Tracker(core=None, llm=Broken()).entry(_conv("CHAT"), consent=True)  # type: ignore[arg-type]
    assert row["source"] == "rules" and row["summary"].startswith("Talked with Arjun")


# ---- /turn rate limit + flush endpoint -----------------------------------------------------------------------
def test_turn_endpoint_rate_limits_per_user_and_flush_endpoint_answers(core_http, uid, monkeypatch):
    monkeypatch.setattr(main_mod, "_engine", TurnEngine(CoreClient(core_http), None, clock=lambda: NOW))
    monkeypatch.setattr(main_mod, "_tracker", None)
    t = [0.0]
    monkeypatch.setattr(main_mod, "_turn_bucket", TokenBucket(rate=1, burst=2, clock=lambda: t[0]))
    api = TestClient(main_mod.app)
    codes = [api.post("/turn", json={"user_id": uid, "text": "किती वाजले"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert api.post("/conversations/flush-idle").json() == {"sent": 0, "open": 1}
