"""Long-term memory of her life: facts extracted after a conversation, deduped, validated by core-api, put into every
LLM call's USER CONTEXT by relevance; "हे लक्षात ठेव" / "हे विसरून जा"."""

import json
from datetime import datetime, timedelta

import httpx
from reasoning_svc import memory as mem
from reasoning_svc.core_client import CoreClient
from reasoning_svc.evon import EvonClient, load_intent_schema
from reasoning_svc.turn import TurnEngine
from reasoning_svc.wellbeing import Conversation, Tracker

NOW = datetime(2026, 10, 6, 9, 0)


class Provider:
    """Answers the facts-extraction call with `facts`, everything else with chat prose; records every request."""

    def __init__(self, facts=None):
        self.facts = facts or []
        self.bodies: list[dict] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        self.bodies.append(body)
        system = body["messages"][0]["content"]
        if "DURABLE" in system:
            content = json.dumps({"facts": self.facts}, ensure_ascii=False)
        elif "short note for the family" in system:
            content = json.dumps({"summary": "chat", "mood": "calm", "severity": "normal", "topics": []})
        else:
            content = "छान वाटलं ऐकून."
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    def last_system(self, marker: str = "You are Arjun") -> str:
        return next(b["messages"][0]["content"] for b in reversed(self.bodies) if marker in b["messages"][0]["content"])


def make(core_http, facts=None):
    provider = Provider(facts)
    client = EvonClient(
        "https://llm.test/v1", "m", http=httpx.Client(transport=httpx.MockTransport(provider)),
        schema=load_intent_schema(), provider="TestAI",
    )
    t = [NOW]
    eng = TurnEngine(
        CoreClient(core_http), client, clock=lambda: t[0], ask_first=False,
        mono=lambda: 1000.0 + (t[0] - NOW).total_seconds(),
    )
    eng.t = t  # type: ignore[attr-defined]
    return eng, provider, client


def conversation(*said: str) -> Conversation:
    conv = Conversation(started=NOW, last=NOW)
    for s in said:
        conv.turns += [("user", s), ("assistant", "ठीक आहे.")]
    return conv


def stored(core_http, uid):
    return [f["fact"] for f in core_http.get(f"/users/{uid}/facts").json()]


def tracker_for(eng, client):
    return Tracker(eng.core, client, clock=lambda: NOW)


# ---- extraction after a conversation -----------------------------------------------------------------------------
def test_facts_are_extracted_stored_and_deduped(core_http, uid):
    eng, provider, client = make(core_http, facts=[
        {"kind": "person", "fact": "आर्यन — नातू", "confidence": 0.9},
        {"kind": "like", "fact": "भजन ऐकायला आवडतं", "confidence": 0.8},
    ])
    tr = tracker_for(eng, client)
    conv = conversation("माझ्या नातवाचं नाव आर्यन आहे", "मला भजन ऐकायला आवडतं")
    assert tr.remember_life(uid, conv, {"language": "mr"}) == 2
    assert sorted(stored(core_http, uid)) == sorted(["आर्यन — नातू", "भजन ऐकायला आवडतं"])
    assert tr.remember_life(uid, conv, {"language": "mr"}) == 0  # the same facts again: refreshed, not duplicated
    assert len(stored(core_http, uid)) == 2


def test_never_store_rules_are_enforced_by_core_api_not_by_the_llm(core_http, uid):
    eng, _, client = make(core_http, facts=[
        {"kind": "note", "fact": "तिचा फोन 9000000000", "confidence": 0.9},
        {"kind": "note", "fact": "पेन्शन येते", "confidence": 0.9},
        {"kind": "place", "fact": "पत्ता गणेश रोड", "confidence": 0.9},
        {"kind": "routine", "fact": "बीपीची गोळी घेते", "confidence": 0.9},
        {"kind": "person", "fact": "सुमन — शेजारीण", "confidence": 0.9},
    ])
    tracker_for(eng, client).remember_life(uid, conversation("सुमन माझी शेजारीण आहे आणि चहाला येते"), {})
    assert stored(core_http, uid) == ["सुमन — शेजारीण"]


def test_a_concern_is_kept_only_with_the_consent_flag(core_http, uid):
    facts = [{"kind": "concern", "fact": "गुडघा दुखतो असं सांगितलं", "confidence": 0.8}]
    eng, _, client = make(core_http, facts=facts)
    tr = tracker_for(eng, client)
    tr.remember_life(uid, conversation("माझा गुडघा खूप दुखतो आहे आजकाल"), {})
    assert stored(core_http, uid) == []
    core_http.patch(f"/users/{uid}", json={"consent_distress_alert": True})
    tr.remember_life(uid, conversation("माझा गुडघा खूप दुखतो आहे आजकाल"), {})
    assert stored(core_http, uid) == ["गुडघा दुखतो असं सांगितलं"]


def test_no_extraction_call_for_a_conversation_with_nothing_to_remember(core_http, uid):
    eng, provider, client = make(core_http)
    tracker_for(eng, client).remember_life(uid, conversation("हो", "नाही"), {})
    assert not any("DURABLE" in b["messages"][0]["content"] for b in provider.bodies)


def test_the_extraction_prompt_forbids_the_never_store_things(core_http, uid):
    eng, provider, client = make(core_http, facts=[])
    tracker_for(eng, client).remember_life(uid, conversation("आज माझा नातू आर्यन आला होता"), {})
    system = provider.last_system("DURABLE")
    assert "NEVER include any number" in system and "medicine" in system and "address" in system


def test_the_conversation_ending_stores_the_facts_through_flush(core_http, uid):
    eng, _, client = make(core_http, facts=[{"kind": "person", "fact": "आर्यन — नातू", "confidence": 0.9}])
    tr = tracker_for(eng, client)
    tr.record(uid, "माझ्या नातवाचं नाव आर्यन आहे आणि तो गोड आहे", "छान.", "CHAT")
    assert tr.flush_idle(NOW + timedelta(minutes=10)) == 1
    assert stored(core_http, uid) == ["आर्यन — नातू"]


# ---- the facts reach every LLM call ------------------------------------------------------------------------------
def test_relevant_facts_are_in_the_user_context_of_the_next_day(core_http, uid):
    eng, provider, _ = make(core_http)
    core_http.post(f"/users/{uid}/facts", json={"fact": "आर्यन — नातू", "kind": "person"})
    core_http.post(f"/users/{uid}/facts", json={"fact": "भजन ऐकायला आवडतं", "kind": "like"})
    eng.t[0] = NOW + timedelta(days=1)
    eng.handle(uid, "आर्यन आज आला होता")
    system = provider.last_system()
    assert "WHAT SHE HAS TOLD YOU" in system and "आर्यन — नातू" in system and "भजन ऐकायला आवडतं" in system


def test_the_matching_fact_comes_first_and_at_most_ten_are_sent(core_http, uid):
    eng, _, _ = make(core_http)
    for name in (["अनिल", "बाळू", "चिंटू", "दत्ता", "एकनाथ", "फुलाबाई", "गोपाळ", "हरी", "इंदू", "जयंत", "कमल", "लता"]):
        core_http.post(f"/users/{uid}/facts", json={"fact": f"{name} — मित्र", "kind": "person"})
    picked = eng.facts.relevant(uid, "लता आज आली होती", NOW, 10)
    assert len(picked) == 10 and picked[0][0]["fact"].startswith("लता") and picked[0][1] is True


def test_an_event_from_yesterday_is_labelled_so_arjun_can_follow_up(core_http, uid):
    eng, provider, _ = make(core_http)
    core_http.post(
        f"/users/{uid}/facts",
        json={"fact": "विमल मैत्रीण भेटायला येणार होती", "kind": "event", "source_date": "2026-10-05"},
    )
    eng.handle(uid, "नमस्कार अर्जुन")
    assert "विमल मैत्रीण भेटायला येणार होती (event, she told you yesterday)" in provider.last_system()


def test_the_companion_call_gets_the_facts_too(core_http, uid):
    eng, provider, _ = make(core_http)
    core_http.post(f"/users/{uid}/facts", json={"fact": "आर्यन — नातू", "kind": "person"})
    eng.handle(uid, "तो आज शाळेत पहिला आला, त्याचं खूप कौतुक झालं")
    assert "आर्यन — नातू" in provider.last_system()


def test_facts_reach_the_context_even_when_core_api_has_none(core_http, uid):
    eng, provider, _ = make(core_http)
    eng.handle(uid, "नमस्कार अर्जुन")
    assert "WHAT SHE HAS TOLD YOU" not in provider.last_system()


def test_matching_facts_are_marked_used(core_http, uid):
    eng, _, _ = make(core_http)
    core_http.post(f"/users/{uid}/facts", json={"fact": "आर्यन — नातू", "kind": "person"})
    eng.handle(uid, "आर्यन आज आला होता")
    assert core_http.get(f"/users/{uid}/facts").json()[0]["last_used"] is not None


# ---- "हे लक्षात ठेव" / "हे विसरून जा" ---------------------------------------------------------------------------
def test_remember_saves_and_reads_back_in_one_line(core_http, uid):
    eng, provider, _ = make(core_http)
    res = eng.handle(uid, "लक्षात ठेव, माझ्या शेजारणीचं नाव सुमन आहे")
    assert res.intent == "MEMORY_SAVED" and res.reply.startswith("ठेवलं: माझ्या शेजारणीचं नाव सुमन आहे")
    assert "?" not in res.reply and not provider.bodies  # no question, no LLM call
    assert stored(core_http, uid) == ["माझ्या शेजारणीचं नाव सुमन आहे"]
    assert core_http.get(f"/users/{uid}/facts").json()[0]["source"] == "explicit"


def test_a_bare_remember_keeps_the_last_thing_she_said(core_http, uid):
    eng, _, _ = make(core_http)
    eng.handle(uid, "मला सकाळी तुळशीची पूजा आवडते")
    res = eng.handle(uid, "हे लक्षात ठेव")
    assert res.intent == "MEMORY_SAVED" and stored(core_http, uid) == ["मला सकाळी तुळशीची पूजा आवडते"]


def test_a_bare_remember_with_nothing_before_it_asks_what(core_http, uid):
    eng, _, _ = make(core_http)
    assert eng.handle(uid, "हे लक्षात ठेव").intent == "MEMORY_ASK"


def test_remember_refuses_numbers_money_and_medicines_with_one_line(core_http, uid):
    eng, _, _ = make(core_http)
    for said in ("लक्षात ठेव, माझा फोन नंबर 9000000000 आहे", "लक्षात ठेव, मी बीपीची गोळी घेते", "लक्षात ठेव, पेन्शन येते"):
        res = eng.handle(uid, said)
        assert res.intent == "MEMORY_REFUSED" and "ठेवत नाही" in res.reply
    assert stored(core_http, uid) == []


def test_forget_deletes_the_last_saved_fact_and_scrubs_the_session(core_http, uid):
    eng, provider, _ = make(core_http)
    eng.handle(uid, "लक्षात ठेव, मला सकाळी तुळशीची पूजा आवडते")
    res = eng.handle(uid, "हे विसरून जा")
    assert res.intent == "MEMORY_FORGOT" and res.reply.startswith("विसरलो:")
    assert stored(core_http, uid) == []
    eng.handle(uid, "मला सकाळी काय आवडतं?")
    sent = json.dumps(provider.bodies[-1]["messages"], ensure_ascii=False)
    assert "तुळशीची पूजा" not in sent  # the forgotten words are gone from the session too


def test_forget_with_words_deletes_the_best_matching_fact(core_http, uid):
    eng, _, _ = make(core_http)
    core_http.post(f"/users/{uid}/facts", json={"fact": "आर्यन — नातू", "kind": "person"})
    core_http.post(f"/users/{uid}/facts", json={"fact": "भजन ऐकायला आवडतं", "kind": "like"})
    res = eng.handle(uid, "आर्यनचं नाव विसरून जा")
    assert res.intent == "MEMORY_FORGOT" and stored(core_http, uid) == ["भजन ऐकायला आवडतं"]


def test_forget_with_no_matching_fact_keeps_the_old_story_behaviour(core_http, uid):
    eng = TurnEngine(CoreClient(core_http), None, clock=lambda: NOW, ask_first=False)
    res = eng.handle(uid, "हे विसर")
    assert res.intent == "FORGET_MEMORY"  # as before: no story, no fact


def test_the_family_deleting_a_fact_removes_it_from_the_next_context(core_http, uid):
    eng, provider, _ = make(core_http)
    fid = core_http.post(f"/users/{uid}/facts", json={"fact": "आर्यन — नातू", "kind": "person"}).json()["id"]
    eng.handle(uid, "आर्यन आला")
    assert "आर्यन — नातू" in provider.last_system()
    core_http.delete(f"/users/{uid}/facts/{fid}")
    eng.facts.invalidate(uid)
    eng.handle(uid, "आर्यन पुन्हा आला")
    assert "आर्यन — नातू" not in provider.last_system()


def test_days_ago_label():
    assert mem.days_ago_label("2026-10-06", NOW) == "today"
    assert mem.days_ago_label("2026-10-05", NOW) == "yesterday"
    assert mem.days_ago_label("2026-10-01", NOW) == "5 days ago"
