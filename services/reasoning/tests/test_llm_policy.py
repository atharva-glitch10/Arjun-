"""When the hosted LLM may be called, what it may do, and what it may say.

Boundaries: 1 (the LLM never touches the DB), 4-6 (AI, no medical advice, medicines), 8 (safety first),
9 (no engagement tricks), 10 (no recipes or facts from memory). Evon is not involved.
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


def _resp(content, usage=None):
    body = {"choices": [{"message": {"content": content}}]}
    if usage:
        body["usage"] = usage
    return httpx.Response(200, json=body)


class Llm:
    """A fake provider that records every request."""

    def __init__(self, intent=None, companion=GOOD):
        self.calls: list[dict] = []
        self.intent, self.companion = intent, companion
        self.on_call = None

    def __call__(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        body["_timeout"] = req.extensions["timeout"]["read"]
        body["_purpose"] = "intent" if body["temperature"] == 0.0 else "companion"
        self.calls.append(body)
        if self.on_call:
            self.on_call(body)
        if body["_purpose"] == "intent":
            return _resp(json.dumps(self.intent or {"intent": "CHAT", "confidence": 0.9, "language": "mr"}))
        return _resp(self.companion)

    @property
    def purposes(self):
        return [c["_purpose"] for c in self.calls]


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
        "औषधाबद्दल विचारायचं आहे दोन गोळ्या घेऊ का",
        "मी तुला सांगितलं ते विसर",
    ],
)
def test_care_commands_never_reach_the_llm(core_http, uid, text):
    llm = Llm()
    make_engine(core_http, llm).handle(uid, text)
    assert llm.calls == [], text


@pytest.mark.parametrize("text", ["मला छातीत दुखतंय", "mala jagaychi iccha nahi"])
def test_emergency_and_distress_run_before_and_without_any_llm_call(core_http, uid, text):
    llm = Llm()
    res = make_engine(core_http, llm).handle(uid, text)
    assert res.mode == "safety" and llm.calls == []


def test_an_ordinary_chat_turn_makes_exactly_one_companion_call(core_http, uid):
    llm = Llm()
    res = make_engine(core_http, llm).handle(uid, STORY)
    assert llm.purposes == ["companion"] and res.mode == "companion" and res.reply == GOOD


def test_an_unreadable_turn_asks_the_llm_for_the_intent(core_http, uid):
    llm = Llm(intent={"intent": "CREATE_REMINDER", "task": "doctor", "date": "2026-10-07", "time": "10:00",
                      "time_ambiguous": False, "confidence": 0.86, "language": "mr"})
    res = make_engine(core_http, llm).handle(uid, "udya doctor")
    assert llm.purposes == ["intent"] and res.source == "llm"
    # it only SUGGESTED: the action is pending and waits for a spoken yes
    assert res.awaiting_confirmation and res.screen == "confirm"
    assert core_http.get(f"/users/{uid}/reminders").json() == []
    assert core_http.get(f"/users/{uid}/actions/pending").json()["payload"]["time"] == "10:00"


def test_unreadable_then_chat_uses_two_calls_in_that_order(core_http, uid):
    llm = Llm()  # intent CHAT, then a companion reply
    res = make_engine(core_http, llm).handle(uid, "हं")
    assert llm.purposes == ["intent", "companion"] and res.mode == "companion"


@pytest.mark.parametrize("intent", ["MED_TAKEN", "MED_SNOOZE", "CONFIRM_YES", "CONFIRM_NO", "FORGET_MEMORY",
                                    "SHARE_STORY_WITH_FAMILY", "COMPLETE_REMINDER", "MEDICAL_QUESTION"])
def test_the_llm_cannot_promote_an_unreadable_turn_into_a_sensitive_intent(core_http, uid, intent):
    llm = Llm(intent={"intent": intent, "confidence": 0.99, "language": "mr"})
    res = make_engine(core_http, llm).handle(uid, "हं")
    assert res.source == "rules" and res.intent == "UNKNOWN" and res.reply == rp.R["mr"]["unknown"]
    assert core_http.get(f"/users/{uid}/actions/pending").json() is None


def test_an_llm_distress_guess_gets_the_fixed_safety_template(core_http, uid):
    llm = Llm(intent={"intent": "DISTRESS", "confidence": 0.9, "language": "mr"})
    res = make_engine(core_http, llm).handle(uid, "हं")
    assert res.mode == "safety" and res.reply == rp.R["mr"]["distress"]


# ---- limits ------------------------------------------------------------------------------------------
def test_one_time_budget_covers_all_calls_in_a_turn(core_http, uid):
    clock = {"t": 0.0}
    llm = Llm()
    llm.on_call = lambda body: clock.__setitem__("t", clock["t"] + 3.0) if body["_purpose"] == "intent" else None
    make_engine(core_http, llm, llm_timeout_s=4.0, mono=lambda: clock["t"]).handle(uid, "हं")
    assert llm.purposes == ["intent", "companion"]
    assert llm.calls[0]["_timeout"] == pytest.approx(4.0) and llm.calls[1]["_timeout"] == pytest.approx(1.0)


def test_with_no_budget_left_the_fixed_line_is_used(core_http, uid):
    clock = {"t": 0.0}
    llm = Llm()
    llm.on_call = lambda body: clock.__setitem__("t", clock["t"] + 3.9)
    res = make_engine(core_http, llm, llm_timeout_s=4.0, mono=lambda: clock["t"]).handle(uid, "हं")
    assert llm.purposes == ["intent"] and res.reply in rp.CHAT["mr"]


def test_a_slow_or_failing_provider_falls_back_to_the_fixed_line(core_http, uid):
    def boom(req):
        raise httpx.ReadTimeout("slow", request=req)

    http = httpx.Client(transport=httpx.MockTransport(boom))
    client = EvonClient("https://llm.test/v1", "m", http=http, schema=load_intent_schema())
    eng = TurnEngine(CoreClient(core_http), client, clock=lambda: NOW)
    res = eng.handle(uid, STORY)
    assert res.mode == "companion" and res.reply in rp.CHAT["mr"]
    assert eng.handle(uid, "हं").reply == rp.R["mr"]["unknown"]  # unreadable + no provider: ask to repeat


def test_only_the_last_four_exchanges_are_sent(core_http, uid):
    llm = Llm()
    eng = make_engine(core_http, llm, history_exchanges=4)
    for i in range(7):
        eng.handle(uid, f"{STORY} {i}")
    last = llm.calls[-1]["messages"]
    assert [m["role"] for m in last] == ["system"] + ["user", "assistant"] * 4 + ["user"]
    assert last[1]["content"].endswith(" 2")  # exchanges 0-2 were dropped
    assert llm.calls[-1]["max_tokens"] == 120


def test_nothing_that_identifies_the_elder_is_sent(core_http, uid):
    core_http.post(f"/users/{uid}/contacts", json={"name": "Rahul", "relation": "son", "phone": "0000000000"})
    llm = Llm()
    make_engine(core_http, llm).handle(uid, STORY)
    sent = json.dumps(llm.calls, ensure_ascii=False)
    assert "Aaji (synthetic)" not in sent and "Rahul" not in sent and "0000000000" not in sent


# ---- what it may say ----------------------------------------------------------------------------------
def test_the_companion_prompt_states_every_boundary(core_http, uid):
    llm = Llm()
    make_engine(core_http, llm).handle(uid, STORY)
    system = llm.calls[0]["messages"][0]["content"].lower()
    for needle in ("marathi", "devanagari", "two short", "listen", "question", "not a human", "medical",
                   "recipes", "facts", "teach", "never say you missed"):
        assert needle in system, needle


@pytest.mark.parametrize(
    "bad,reason",
    [
        ("मी माणूस आहे, मला पण भूक लागली.", "human"),
        ("I am a real person like you.", "human"),
        ("मला तुमची खूप आठवण आली.", "missed_you"),
        ("I missed you so much.", "missed_you"),
        ("रोज सकाळी 500 mg ची गोळी घ्या.", "medical"),
        ("तुम्ही हे औषध घ्या आणि बरं वाटेल.", "medical"),
        ("पुरणपोळीसाठी साहित्य: दोन कप गव्हाचं पीठ.", "recipe_fact"),
        ("भारताची राजधानी दिल्ली आहे.", "recipe_fact"),
        ("That sounds nice, tell me more.", "script"),
    ],
)
def test_replies_that_break_a_boundary_are_rejected(bad, reason):
    text, reasons = sanitize_companion(bad, "mr")
    assert text is None and reason in reasons


def test_a_rejected_llm_reply_is_replaced_by_the_fixed_line(core_http, uid):
    llm = Llm(companion="मी माणूस आहे, मला तुमची आठवण आली.")
    res = make_engine(core_http, llm).handle(uid, STORY)
    assert res.reply in rp.CHAT["mr"] and "माणूस" not in res.reply


def test_a_good_reply_passes_and_a_long_one_is_cut_to_two_sentences():
    assert sanitize_companion(GOOD, "mr") == (GOOD, [])
    long = "छान वाटलं. बाग सुंदर असेल. मग पुढे काय झालं? तिथे कोण होतं?"
    text, reasons = sanitize_companion(long, "mr")
    assert text == "छान वाटलं. बाग सुंदर असेल." and reasons == []
