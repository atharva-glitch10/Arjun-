"""2026-11-09 log bugs: (1) a call request was answered as CHAT (the reply claimed a call, none was made, no Telegram alert);
(2) every turn fell back to the rules with route_reason invalid_json (the understanding JSON was cut off at max_tokens).
All providers are mocked."""

import json

import httpx
import pytest
from reasoning_svc import evon as evon_mod
from reasoning_svc import replies as rp
from reasoning_svc.callcmd import is_call_request, relation_matches, role_of
from reasoning_svc.core_client import CoreClient, CoreError
from reasoning_svc.evon import EvonClient, _parse_json_object, load_intent_schema
from reasoning_svc.turn import TurnEngine
from test_web_search import Llm, _understand, make


def acted(res):
    return (res.action or {}).get("type") not in (None, "", "none")


# ---- 1. invalid_json: the parser, on real-shaped bad outputs -----------------------------------------------------------
# what gemini-flash-lite really returned for "राहुल को कॉल करो ...": every Devanagari letter escaped, cut off at max_tokens
TRUNCATED = (
    '{"intent": "video_call", "slots": {"task": null, "date": null, "time": null, "time_ambiguous": false, "query": null, '
    '"contact": "\\u0930\\u093e\\u0939\\u0941\\u0932", "confirm": null}, "reply": "\\u0930\\u093e\\u0939\\u0941\\u0932\\u0932\\u093e '
    '\\u0915\\u0949\\u0932 \\u0915\\u0930\\u0924\\u094b\\u092f.", "confidence": 0.99, "answer_mode": null, "entity": null, "query_en": null, "queries": null, "time_sens'
)


@pytest.mark.parametrize(
    "raw,check",
    [
        ('```json\n{"intent": "chat", "reply": "ठीक"}\n```', lambda d: d["reply"] == "ठीक"),
        ('<think>the user said {x}</think>{"intent": "chat"}', lambda d: d["intent"] == "chat"),
        ('Sure! Here it is: {"intent": "chat", "slots": {"a": [1, 2]}} Hope that helps.', lambda d: d["slots"]["a"] == [1, 2]),
        ('{"intent": "chat", "slots": {"a": 1,}, "reply": "x",}', lambda d: d["slots"]["a"] == 1),
        ("{“intent”: “chat”, “reply”: “हो”}", lambda d: d["reply"] == "हो"),
        ('{"intent": "chat", "reply": "line one\nline two"}', lambda d: "line two" in d["reply"]),
        ('{"intent": "chat", "reply": "a {brace} inside"}', lambda d: d["reply"] == "a {brace} inside"),
        (TRUNCATED, lambda d: d["intent"] == "video_call" and d["slots"]["contact"] == "राहुल"),  # cut mid-key: repaired
        ('{"intent": "chat", "reply": "x", "confidence":', lambda d: d["intent"] == "chat" and "confidence" not in d),
        ('{"intent": "chat", "reply": "cut off in the mid', lambda d: d["intent"] == "chat" and d["reply"].startswith("cut off")),
    ],
)
def test_the_parser_recovers_real_shaped_bad_json(raw, check):
    data = _parse_json_object(raw)
    assert data is not None and check(data)


@pytest.mark.parametrize("raw", ["", None, "no json at all", "{", "[1, 2]", "<think>unclosed {"])
def test_the_parser_still_refuses_what_is_not_an_object(raw):
    assert _parse_json_object(raw) is None


# ---- the call: automatic retry, token room, rate ---------------------------------------------------------------------
def _resp(content, finish="stop"):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": finish}]})


class Scripted:
    """A provider that answers from a list, recording each request body."""

    def __init__(self, *answers):
        self.answers, self.bodies = list(answers), []

    def __call__(self, req):
        self.bodies.append(json.loads(req.content))
        content, finish = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return _resp(content, finish)


def client(handler):
    return EvonClient("https://llm.test/v1", "m", http=httpx.Client(transport=httpx.MockTransport(handler)),
                      schema=load_intent_schema(), provider="T")


GOOD = json.dumps({"intent": "video_call", "slots": {"contact": "राहुल"}, "reply": "", "confidence": 0.98}, ensure_ascii=False)


def test_the_understanding_call_has_room_for_a_full_object_and_asks_for_compact_json():
    from datetime import datetime

    h = Scripted((GOOD, "stop"))
    c = client(h)
    out = c.understand_turn("राहुल को कॉल करो", "mr", datetime(2026, 11, 9, 9, 0))
    assert out["intent"] == "video_call" and h.bodies[0]["max_tokens"] == evon_mod.UNDERSTAND_MAX_TOKENS >= 700
    assert "KEEP THE JSON COMPACT" in h.bodies[0]["messages"][0]["content"]
    assert c.invalid_json_rate() == 0.0


def test_a_cut_off_answer_is_repaired_without_a_second_call():
    from datetime import datetime

    h = Scripted((TRUNCATED, "length"))
    out = client(h).understand_turn("राहुल को कॉल करो", "mr", datetime(2026, 11, 9, 9, 0))
    assert out["intent"] == "video_call" and len(h.bodies) == 1


def test_unparseable_output_gets_exactly_one_retry_that_asks_for_valid_json():
    from datetime import datetime

    h = Scripted(("{not json at all", "length"), (GOOD, "stop"))
    c = client(h)
    out = c.understand_turn("राहुल को कॉल करो", "mr", datetime(2026, 11, 9, 9, 0))
    assert out["intent"] == "video_call" and len(h.bodies) == 2
    retry = h.bodies[1]
    assert "ONLY one valid, COMPACT JSON" in retry["messages"][-1]["content"] and retry["max_tokens"] == evon_mod.UNDERSTAND_RETRY_MAX_TOKENS
    assert c.usage["json_invalid_first"] == 1 and c.usage["json_retry_ok"] == 1 and c.invalid_json_rate() == 1.0


def test_two_bad_answers_give_up_after_one_retry_and_count_it():
    from datetime import datetime

    h = Scripted(("{not json", "length"))
    c = client(h)
    assert c.understand_turn("x", "mr", datetime(2026, 11, 9, 9, 0)) is None and len(h.bodies) == 2
    assert c.usage["json_invalid"] == 1


# ---- 2. call intent in the rules fallback (no LLM at all) ------------------------------------------------------------------
CALLS = [
    "राहुल को कॉल करो फिरसे राहुल से बात करनी है", "राहुल से बात करनी है राहुल को कॉल लगाओ जरा", "राहुलला कॉल कर", "राहुलला कॉल करा",
    "राहुलला फोन लाव", "राहुलला फोन लावा", "राहुलला फोन जोड", "राहुल को कॉल करो", "राहुल को कॉल लगाओ", "राहुल को फोन लगाओ",
    "राहुल को फोन करो", "राहुल से बात करनी है", "राहुलशी बोलायचंय", "मला राहुलला फोन करायचाय", "मुलाला फोन लावा", "बेटे को फोन लगाओ",
    "call my son", "call Rahul", "please call Rahul now", "i want to call Rahul", "rahul ko call lagao", "rahulla phone laav", "call rahul kar",
    "राहुल को काल करो",
]
NOT_CALLS = ["राहुलला फोन करू नको", "राहुलने कॉल केला", "राहुलला फोन करायची आठवण ठेव", "remind me to call Rahul", "आज पाऊस पडेल का",
             "माझा फोन हरवला", "his call was long", "what is the call time", "राहुल को कॉल मत करो"]


@pytest.fixture()
def rahul(core_http, uid):
    contact = core_http.post(f"/users/{uid}/contacts", json={"name": "Rahul", "relation": "son"}).json()
    doctor = core_http.post(f"/users/{uid}/contacts", json={"name": "Dr Kulkarni", "relation": "doctor"}).json()
    return contact, doctor


@pytest.mark.parametrize("text", [c for c in CALLS if "rahulla" not in c and "call rahul kar" not in c])
def test_named_and_role_call_requests_are_calls_with_the_right_contact(core_http, uid, rahul, text):
    contact, doctor = rahul
    res = TurnEngine(CoreClient(core_http), evon=None, ask_first=False).handle(uid, text)
    assert res.intent == "VIDEO_CALL", text
    assert res.action["contact_id"] == str(contact["id"]) != str(doctor["id"])  # the family member, never the doctor


@pytest.mark.parametrize("text", NOT_CALLS)
def test_past_negated_reminder_and_unrelated_sentences_are_not_calls(text):
    assert not is_call_request(text)


def test_role_words_map_to_the_primary_family_member():
    assert role_of("मुलाला फोन लावा") == "son" and role_of("बेटे को फोन लगाओ") == "son" and role_of("call my son") == "son"
    assert role_of("मुलीला फोन लाव") == "daughter" and role_of("call Rahul") is None
    assert relation_matches("Son", "son") and relation_matches("मुलगा", "son") and not relation_matches("doctor", "son")


def test_a_daughter_is_called_when_she_is_asked_for_and_the_son_is_the_fallback(core_http, uid, rahul):
    daughter = core_http.post(f"/users/{uid}/contacts", json={"name": "Sita", "relation": "daughter"}).json()
    eng = TurnEngine(CoreClient(core_http), evon=None, ask_first=False)
    assert eng.handle(uid, "मुलीला फोन लावा").action["contact_id"] == str(daughter["id"])
    assert eng.handle(uid, "मुलाला फोन लावा").action["contact_id"] == str(rahul[0]["id"])


# ---- 4. the elder is told only after core-api placed the call ------------------------------------------------------------
def test_the_call_is_placed_through_core_api_before_the_elder_is_told(core_http, uid, rahul, monkeypatch):
    eng = TurnEngine(CoreClient(core_http), evon=None, ask_first=False)
    placed = []
    monkeypatch.setattr(eng.core, "start_call", lambda u, cid: placed.append((u, cid)) or {"id": 1})
    res = eng.handle(uid, "राहुल को कॉल करो")
    assert placed == [(uid, rahul[0]["id"])] and res.action and "थांबा" in res.reply


@pytest.mark.parametrize("status", [503, 500, 404])
def test_a_call_core_api_could_not_place_is_never_announced(core_http, uid, rahul, monkeypatch, status):
    eng = TurnEngine(CoreClient(core_http), evon=None, ask_first=False)

    def fail(u, cid):
        raise CoreError(status, "family call link unavailable")

    monkeypatch.setattr(eng.core, "start_call", fail)
    res = eng.handle(uid, "राहुल को कॉल करो")  # Hindi in, Hindi line out
    assert res.reply == rp.R["hi"]["call_failed"] and not acted(res)


def test_a_network_failure_is_the_same_honest_line(core_http, uid, rahul, monkeypatch):
    eng = TurnEngine(CoreClient(core_http), evon=None, ask_first=False)

    def down(u, cid):
        raise httpx.ConnectError("core-api down")

    monkeypatch.setattr(eng.core, "start_call", down)
    res = eng.handle(uid, "call Rahul")
    assert res.reply == rp.R["mr"]["call_failed"] and not acted(res)


# ---- 3. no action claims without an action ---------------------------------------------------------------------------------
def llm_chat(reply):
    payload = _understand(web=False)
    payload.update(reply=reply, answer_mode="know", know_confidence=0.99)
    return Llm(payload)


def test_a_chat_reply_that_claims_a_call_runs_the_call_instead(core_http, uid, rahul):
    res = make(core_http, llm_chat("मी राहुलला फोन जोडतो.")).handle(uid, "राहुल को कॉल करो फिरसे राहुल से बात करनी है")
    assert res.intent == "VIDEO_CALL" and res.action["contact_id"] == str(rahul[0]["id"])


def test_a_call_claim_without_a_call_request_becomes_a_clarifying_question(core_http, uid, rahul):
    res = make(core_http, llm_chat("ठीक आहे, मी फोन लावतो.")).handle(uid, "बरं मग काय करायचं आता")
    assert res.intent == "CHAT" and not acted(res) and "Rahul" in res.reply and "लावतो" not in res.reply


def test_a_play_claim_without_an_action_becomes_a_question(core_http, uid):
    res = make(core_http, llm_chat("ठीक आहे, भजन लावतो.")).handle(uid, "आता थोडं बरं वाटतंय")
    assert res.reply == rp.R["mr"]["claim_play"] and not acted(res)


def test_a_reminder_claim_without_a_reminder_becomes_a_question(core_http, uid):
    res = make(core_http, llm_chat("ठीक आहे, मी आठवण ठेवतो.")).handle(uid, "आज खूप कामं आहेत")
    assert res.reply == rp.R["mr"]["ask_task"]


def test_ordinary_chat_is_left_alone(core_http, uid):
    res = make(core_http, llm_chat("छान, बागेत फिरणं चांगलं असतं.")).handle(uid, "मी रोज बागेत जातो")
    assert res.reply == "छान, बागेत फिरणं चांगलं असतं."
