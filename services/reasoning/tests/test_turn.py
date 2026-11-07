import json

import httpx
from reasoning_svc.evon import EvonClient, load_intent_schema
from reasoning_svc.turn import TurnEngine


def _reminders(core_http, uid):
    return core_http.get(f"/users/{uid}/reminders").json()


def test_prisma_detected_language_reaches_turn_language(engine, uid):
    result = engine.handle(uid, "hello there", "mr-IN")
    assert result.language == "mr"


def test_prisma_detected_language_allows_ten_language_reply_selection(engine, uid):
    result = engine.handle(uid, "சரி", "ta-IN")
    assert result.language == "ta"


def test_relative_time_uses_configured_wake_time_then_confirm_then_save(engine, core_http, uid):
    res = engine.handle(uid, "udya sakali doctor la jaycha aahe, remind kar")
    assert res.intent == "CREATE_REMINDER" and res.awaiting_confirmation
    assert _reminders(core_http, uid) == []  # nothing saved before spoken confirmation
    pending = core_http.get(f"/users/{uid}/actions/pending").json()
    assert pending["payload"]["date"] == "2026-10-07"
    assert pending["payload"]["time"] == "07:00"  # wake_time default
    assert "doctor" in pending["payload"]["task"]

    res = engine.handle(uid, "ho")
    assert res.intent == "CONFIRM_YES"
    rows = _reminders(core_http, uid)
    assert len(rows) == 1 and rows[0]["due_at"].startswith("2026-10-07T07:00")


def test_ambiguous_ampm_asks_then_resolves(engine, core_http, uid):
    res = engine.handle(uid, "udya 10 vajta doctor la jaycha remind kar")
    assert res.awaiting_confirmation
    assert core_http.get(f"/users/{uid}/actions/pending").json() is None  # still asking
    assert "10" in res.reply
    res = engine.handle(uid, "sakali")
    assert res.awaiting_confirmation
    pending = core_http.get(f"/users/{uid}/actions/pending").json()
    assert pending["payload"]["time"] == "10:00"


def test_24h_time_is_not_ambiguous(engine, core_http, uid):
    engine.handle(uid, "aaj 20:30 vajta pooja remind kar")
    assert core_http.get(f"/users/{uid}/actions/pending").json()["payload"]["time"] == "20:30"


def test_missing_date_is_asked_not_guessed(engine, core_http, uid):
    res = engine.handle(uid, "ratri 8 vajta pooja remind kar")
    assert core_http.get(f"/users/{uid}/actions/pending").json() is None
    assert "दिवशी" in res.reply
    engine.handle(uid, "udya")
    assert core_http.get(f"/users/{uid}/actions/pending").json()["payload"]["time"] == "20:00"


def test_meal_relative_time(engine, core_http, uid):
    engine.handle(uid, "udya dupari jevna nantar pooja remind kar")
    assert core_http.get(f"/users/{uid}/actions/pending").json()["payload"]["time"] == "13:30"


def test_yes_without_pending_saves_nothing(engine, core_http, uid):
    res = engine.handle(uid, "ho")
    assert res.intent == "CONFIRM_YES"
    assert _reminders(core_http, uid) == []


def test_no_cancels_pending(engine, core_http, uid):
    engine.handle(uid, "udya 19:00 vajta walk remind kar")
    res = engine.handle(uid, "nahi")
    assert res.intent == "CONFIRM_NO"
    assert _reminders(core_http, uid) == []
    assert core_http.get(f"/users/{uid}/actions/pending").json() is None


def test_list_today_reads_from_sql(engine, core_http, uid):
    core_http.post(
        f"/users/{uid}/reminders", json={"task": "BP tablet", "date": "2026-10-06", "time": "20:00"}
    )
    res = engine.handle(uid, "aaj kay kay aahe")
    assert res.intent == "LIST_TODAY" and "BP tablet" in res.reply


def test_get_appointment(engine, core_http, uid):
    assert engine.handle(uid, "doctor chi bhet kadhi aahe").intent == "GET_APPOINTMENT"
    core_http.post(
        f"/users/{uid}/appointments",
        json={"title": "Eye check", "starts_at": "2026-10-09T11:00:00", "location": "Pune"},
    )
    res = engine.handle(uid, "doctor chi bhet kadhi aahe")
    assert "Eye check" in res.reply and "Pune" in res.reply


def test_complete_reminder_requires_confirmation(engine, core_http, uid):
    core_http.post(
        f"/users/{uid}/reminders", json={"task": "tablet", "date": "2026-10-06", "time": "20:00"}
    )
    res = engine.handle(uid, "tablet ghetli")
    assert res.intent == "COMPLETE_REMINDER" and res.awaiting_confirmation
    assert _reminders(core_http, uid)[0]["status"] == "pending"
    engine.handle(uid, "ho")
    assert _reminders(core_http, uid)[0]["status"] == "done"


def test_call_family_uses_contacts_from_sql(engine, core_http, uid):
    assert "नंबर" in engine.handle(uid, "mulila phone karaycha aahe").reply  # no contacts
    core_http.post(f"/users/{uid}/contacts", json={"name": "Rahul", "relation": "son"})
    res = engine.handle(uid, "mulila phone karaycha aahe")
    assert res.intent == "CALL_FAMILY_REMINDER" and "Rahul" in res.reply


def test_ai_disclosure(engine, uid):
    res = engine.handle(uid, "tu manus aahes ka")
    assert "एआय" in res.reply and "माणूस नाही" in res.reply


def test_story_private_until_user_shares(engine, core_http, uid):
    long_story = "mi lahanpani gavat khup khelayche ani amhi roj nadivar jaycho mag aaji amhala bhakri dayachi ani goshti sangaychi"
    res = engine.handle(uid, long_story)
    assert res.intent == "CHAT" and res.awaiting_confirmation
    engine.handle(uid, "ho")  # consent to keep it privately
    assert core_http.get(f"/users/{uid}/memory-book").json() == []

    res = engine.handle(uid, "hi goshta kutumbala sang")
    assert res.intent == "SHARE_STORY_WITH_FAMILY"
    assert core_http.get(f"/users/{uid}/memory-book").json() == []  # not shared yet
    engine.handle(uid, "ho")
    assert len(core_http.get(f"/users/{uid}/memory-book").json()) == 1


def test_forget_deletes_story(engine, core_http, uid):
    core_http.post(f"/users/{uid}/stories", json={"summary": "private memory"})
    res = engine.handle(uid, "he visar")
    assert res.intent == "FORGET_MEMORY"
    assert core_http.get(f"/users/{uid}/stories/latest").json() is None


def test_nako_without_context_declines_and_blocks_opener(engine, core_http, uid):
    assert engine.opener(uid) is not None  # allowed: interests set, in hours, not declined
    res = engine.handle(uid, "nako")
    assert res.intent == "DECLINE_TOPIC"
    assert engine.opener(uid) is None  # no re-ask that day


def test_opener_never_supplies_facts(engine, uid):
    text = engine.opener(uid)
    assert "cooking" in text  # asks the user to teach; no recipe content


def test_unknown_asks_to_repeat(engine, uid):
    assert engine.handle(uid, "hmm").intent == "UNKNOWN"


def test_past_time_is_rejected_by_core(engine, core_http, uid):
    res = engine.handle(uid, "aaj 06:30 vajta tea remind kar")
    assert core_http.get(f"/users/{uid}/actions/pending").json() is None
    assert res.awaiting_confirmation  # asks for another time


# ---- Evon client ------------------------------------------------------------------------------
def _evon(handler) -> EvonClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return EvonClient("http://evon.test/v1", "evon", http=http, schema=load_intent_schema())


def _chat_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_evon_request_contract_and_valid_output():
    seen: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(json.loads(req.content))
        return _chat_response(
            json.dumps({"intent": "LIST_TODAY", "confidence": 0.9, "language": "mr"})
        )

    from datetime import datetime

    out = _evon(handler).extract_intent("aaj kay", "mr", datetime(2026, 10, 6), "07:00", "13:00", "20:00")
    assert out and out["intent"] == "LIST_TODAY"
    body = seen[0]
    assert body["temperature"] == 0.0
    assert body["chat_template_kwargs"] == {"enable_thinking": False}


def test_evon_invalid_json_retries_once_then_none():
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return _chat_response("not json")

    from datetime import datetime

    out = _evon(handler).extract_intent("x", "mr", datetime(2026, 10, 6), "07:00", "13:00", "20:00")
    assert out is None and calls["n"] == 2


def test_evon_schema_violation_falls_back_to_rules(core_http, uid):
    from datetime import datetime

    from reasoning_svc.core_client import CoreClient

    def handler(req: httpx.Request) -> httpx.Response:
        return _chat_response(json.dumps({"intent": "DROP_TABLE", "confidence": 2, "language": "xx"}))

    eng = TurnEngine(CoreClient(core_http), _evon(handler), clock=lambda: datetime(2026, 10, 6, 9, 0))
    res = eng.handle(uid, "aaj kay kay aahe")
    assert res.intent == "LIST_TODAY" and res.source == "rules"


def test_evon_intent_is_used_when_valid(core_http, uid):
    from datetime import datetime

    from reasoning_svc.core_client import CoreClient

    def handler(req: httpx.Request) -> httpx.Response:
        return _chat_response(
            json.dumps(
                {"intent": "CREATE_REMINDER", "task": "doctor visit", "date": "2026-10-07",
                 "time": "10:00", "time_ambiguous": False, "confidence": 0.86, "language": "mr"}
            )
        )

    eng = TurnEngine(CoreClient(core_http), _evon(handler), clock=lambda: datetime(2026, 10, 6, 9, 0))
    res = eng.handle(uid, "udya doctor")  # the rules cannot read this, so the LLM is asked
    assert res.source == "llm" and res.awaiting_confirmation
    assert core_http.get(f"/users/{uid}/actions/pending").json()["payload"]["time"] == "10:00"


# ---- companion conversation context ------------------------------------------------------------
def _companion_engine(core_http, clock):
    from reasoning_svc.core_client import CoreClient

    companion_bodies: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        if body["temperature"] == 0.0:  # intent extraction
            return _chat_response(json.dumps({"intent": "CHAT", "confidence": 0.9, "language": "mr"}))
        companion_bodies.append(body)
        return _chat_response(f"छान, पुढे काय झालं? {len(companion_bodies)}")

    return TurnEngine(CoreClient(core_http), _evon(handler), clock=clock), companion_bodies


def test_companion_gets_this_conversations_history_and_interests(core_http, uid):
    from datetime import datetime

    eng, bodies = _companion_engine(core_http, lambda: datetime(2026, 10, 6, 9, 0))
    eng.handle(uid, "आज मी बागेत फिरायला गेलो होतो")
    eng.handle(uid, "मग तिथे माझे जुने मित्र भेटले")
    first, second = bodies
    assert [m["role"] for m in first["messages"]] == ["system", "user"]
    assert [m["role"] for m in second["messages"]] == ["system", "user", "assistant", "user"]
    assert second["messages"][1]["content"] == "आज मी बागेत फिरायला गेलो होतो"
    assert "cooking" in second["messages"][0]["content"]  # interest hint, to be taught not told


def test_companion_history_expires_after_idle(core_http, uid):
    from datetime import datetime, timedelta

    now = [datetime(2026, 10, 6, 9, 0)]
    eng, bodies = _companion_engine(core_http, lambda: now[0])
    eng.handle(uid, "आज मी बागेत फिरायला गेलो होतो")
    now[0] += timedelta(minutes=31)
    eng.handle(uid, "मग तिथे माझे जुने मित्र भेटले")
    assert [m["role"] for m in bodies[1]["messages"]] == ["system", "user"]


def test_distress_keeps_the_history_and_adds_a_safety_note(core_http, uid):
    from datetime import datetime

    eng, bodies = _companion_engine(core_http, lambda: datetime(2026, 10, 6, 9, 0))
    eng.handle(uid, "आज मी बागेत फिरायला गेलो होतो")
    assert eng.handle(uid, "mala jagaychach nahi").mode == "safety"
    eng.handle(uid, "मग तिथे माझे जुने मित्र भेटले")
    msgs = bodies[-1]["messages"]
    # the story and the safety moment are still there (history is no longer wiped), and the prompt says to be gentle
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user", "assistant", "user"]
    assert "safety moment" in msgs[0]["content"] and "Be gentle" in msgs[0]["content"]


def test_other_llm_options_key_header_and_no_vllm_only_field():
    seen: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(json.loads(req.content))
        return _chat_response("ठीक आहे")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    plain = EvonClient("http://llm.test/v1", "m", http=http, schema=load_intent_schema(),
                       send_template_kwargs=False)
    plain.companion_reply("namaskar", "mr")
    assert "chat_template_kwargs" not in seen[0]
    _evon(handler).companion_reply("x", "mr")  # default keeps the vLLM field for Evon
    assert seen[1]["chat_template_kwargs"] == {"enable_thinking": False}

    keyed = EvonClient("http://llm.test/v1", "m", schema=load_intent_schema(), api_key="k123")
    assert keyed.http.headers["authorization"] == "Bearer k123"
    assert "authorization" not in EvonClient("http://llm.test/v1", "m", schema=load_intent_schema()).http.headers


def test_repeat_reuses_simplified_reply_and_keeps_exact_numbers(engine, core_http, uid):
    class Simplifier:
        value = "उद्या 11:30 वाजता या."

        def simplify_reply(self, reply, language, timeout=None):
            return self.value

    simplifier = Simplifier()
    engine.evon = simplifier
    engine._last_arjun_reply[uid] = "कृपया उद्या 10:30 वाजता येथे या."
    engine._last_reply_simplifiable[uid] = True
    result = engine.handle(uid, "पुन्हा सांग")
    assert result.intent == "REPEAT"
    assert result.reply == "कृपया उद्या 10:30 वाजता येथे या."
    simplifier.value = "उद्या 10:30 वाजता या."
    result = engine.handle(uid, "परत सांग")
    assert result.reply == "उद्या 10:30 वाजता या."
    assert engine.handle(uid, "काय?").intent == "REPEAT"
    assert TurnEngine._same_numbers("वेळ 10:30 आणि 25 आहे", "वेळ 10:30 आणि 25 आहे")
    assert not TurnEngine._same_numbers("वेळ 10:30", "वेळ 11:30")


def test_repeat_auto_switch_and_voice_style_reset(engine, core_http, uid):
    engine._last_arjun_reply[uid] = "आजचा दिवस छान जावो."
    assert engine.handle(uid, "समजलं नाही").intent == "REPEAT"
    assert engine.handle(uid, "परत सांग").intent == "REPEAT"
    profile = core_http.get(f"/users/{uid}").json()["speech_style"]
    assert profile == {"rate": "slow", "volume": "normal", "simple": True}
    result = engine.handle(uid, "नेहमीसारखं बोल")
    assert result.intent == "SPEAK_NORMAL"
    assert core_http.get(f"/users/{uid}").json()["speech_style"] == {"rate": "normal", "volume": "normal", "simple": False}


def test_explicit_speech_style_controls(engine, core_http, uid):
    assert engine.handle(uid, "हळू बोल").intent == "SPEAK_SLOWER"
    assert core_http.get(f"/users/{uid}").json()["speech_style"]["rate"] == "slow"
    assert engine.handle(uid, "मोठ्याने बोल").intent == "SPEAK_LOUDER"
    assert core_http.get(f"/users/{uid}").json()["speech_style"]["volume"] == "loud"
