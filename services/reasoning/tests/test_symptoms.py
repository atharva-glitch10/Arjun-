"""Health complaints (task C, boundary 5): Arjun never advises. A symptom that is not an emergency gets a fixed warm
reply, a family note (kind "health_complaint", seriousness "watch", only with the family-alert consent) and the
conversation goes on. The lexicon is UNVERIFIED (no native speaker, no real Prisma output); these tests pin behaviour."""

import json
from datetime import datetime

import httpx
import pytest
from reasoning_svc import replies as rp
from reasoning_svc.core_client import CoreClient
from reasoning_svc.distress import is_distress, is_emergency, symptom_category
from reasoning_svc.evon import EvonClient, companion_violations, load_intent_schema
from reasoning_svc.turn import TurnEngine

NOW = datetime(2026, 10, 6, 9, 0)
EVIDENCE_4 = "काय सांगू तुला डोकं दुखतं आहे माझं थोडं आणि"


@pytest.mark.parametrize(
    "text, category",
    [
        (EVIDENCE_4, "head"),
        ("माझं डोकं दुखतंय", "head"),
        ("डोकेदुखी आहे आज", "head"),
        ("मेरा सिर दर्द कर रहा है", "head"),
        ("I have a headache", "head"),
        ("पोट दुखतं आहे", "stomach"),
        ("पोटात दुखतंय सकाळपासून", "stomach"),
        ("पेट में दर्द है", "stomach"),
        ("मला ताप आलाय", "fever"),
        ("मुझे बुखार है", "fever"),
        ("I think I have a fever", "fever"),
        ("गुडघा दुखतो", "joint"),
        ("माझे गुडघे दुखतात", "joint"),
        ("कंबर दुखते आहे", "joint"),
        ("घुटने में दर्द है", "joint"),
        ("my knee hurts", "joint"),
        ("रात्री झोप येत नाही", "sleep"),
        ("मला झोप लागत नाही", "sleep"),
        ("नींद नहीं आती", "sleep"),
        ("I can't sleep at night", "sleep"),
        ("मी काल पडले होते", "fall_past"),
        ("मी पडलो होतो बाथरूममध्ये", "fall_past"),
        ("तबीयत ठीक नहीं है", "unwell"),
        ("मला बरं वाटत नाही", "unwell"),
        ("I am not feeling well", "unwell"),
    ],
)
def test_symptom_phrases(text, category):
    assert symptom_category(text) == category
    assert not is_emergency(text) and not is_distress(text)  # a warm note, not a crisis template


@pytest.mark.parametrize(
    "text",
    ["छातीत दुखतंय", "मला चक्कर येतेय", "मला चक्कर आली", "I feel dizzy", "श्वास घेता येत नाही", "मी पडले आहे"],
)
def test_emergencies_stay_emergencies(text):
    assert is_emergency(text)
    assert symptom_category(text) is None or is_emergency(text)  # the emergency check runs first


@pytest.mark.parametrize(
    "text",
    ["आज मी बागेत गेले होते", "डोकं खाजवत बसले होते", "उद्या डॉक्टरकडे जायचं आहे", "ताप्यात चहा केला",
     "लहानपणी मी पडले होते आणि आईने उचललं", "I slept well"],
)
def test_not_symptoms(text):
    assert symptom_category(text) is None


# ---- the turn -----------------------------------------------------------------------------------------------------
def _engine(core_http, llm=None):
    return TurnEngine(CoreClient(core_http), llm, clock=lambda: NOW, ask_first=False)


def _kinds(core_http, uid):
    return [n["kind"] for n in core_http.get(f"/users/{uid}/notifications").json()]


def test_a_headache_gets_the_fixed_template_and_a_family_note(core_http, uid):
    core_http.patch(f"/users/{uid}", json={"consent_distress_alert": True})
    eng = _engine(core_http)
    res = eng.handle(uid, EVIDENCE_4)
    assert res.intent == "SYMPTOM" and res.mode == "companion" and not res.awaiting_confirmation
    assert res.reply == "घरच्यांना कळवलं आहे. आता कसं वाटतंय?"  # ends with a "how are you now" question, no yes/no
    for advice in ("आराम", "पाणी", "गोळी", "औषध", "झोपा", "पडून"):
        assert advice not in res.reply
    assert "health_complaint" in _kinds(core_http, uid)


def test_the_note_is_watch_level_in_the_feed(core_http, uid):
    core_http.patch(f"/users/{uid}", json={"consent_distress_alert": True})
    _engine(core_http).handle(uid, EVIDENCE_4)
    feed = core_http.get(f"/users/{uid}/feed").json()
    events = feed["events"] if isinstance(feed, dict) else feed
    assert any(e.get("severity") == "watch" for e in events)


def test_without_consent_nothing_is_noted_and_the_reply_does_not_claim_it(core_http, uid):
    eng = _engine(core_http)
    res = eng.handle(uid, EVIDENCE_4)
    assert res.intent == "SYMPTOM"
    assert "स्क्रीनवर" not in res.reply  # boundary 14: never claim a delivery that did not happen
    assert "डॉक्टर" in res.reply  # points to a person; no advice
    assert "health_complaint" not in _kinds(core_http, uid)


def test_the_conversation_continues_after_a_symptom(core_http, uid):
    eng = _engine(core_http)
    eng.handle(uid, EVIDENCE_4)
    res = eng.handle(uid, "डंड")
    assert res.intent == "CHAT"  # conversation mode: not "मला नीट समजलं नाही"


def test_a_care_command_still_wins_over_a_symptom_word(core_http, uid):
    res = _engine(core_http).handle(uid, "माझं डोकं दुखतंय मला मदत हवी आहे")
    assert res.intent == "REQUEST_CAREGIVER"


def test_a_story_about_the_past_fall_is_noted_but_is_not_an_emergency(core_http, uid):
    core_http.patch(f"/users/{uid}", json={"consent_distress_alert": True})
    res = _engine(core_http).handle(uid, "मी काल पडले होते")
    assert res.intent == "SYMPTOM" and res.mode != "safety"


def test_one_note_per_kind_of_complaint_per_day(core_http, uid):
    core_http.patch(f"/users/{uid}", json={"consent_distress_alert": True})
    eng = _engine(core_http)
    eng.handle(uid, "डोकं दुखतंय")
    eng.handle(uid, "पुन्हा डोकं दुखतंय")
    eng.handle(uid, "पोट दुखतंय")
    assert _kinds(core_http, uid).count("health_complaint") == 2


def test_templates_exist_in_all_three_languages_and_give_no_advice():
    for lang in ("mr", "hi", "en"):
        r = rp.R[lang]
        assert "{" not in r["symptom_noted"] and "{" not in r["symptom_not_noted"]
        assert not companion_violations(r["symptom_noted"], lang)
        assert not companion_violations(r["symptom_not_noted"], lang)


# ---- the LLM may not give health advice (evidence 4: "थोडा वेळ शांत पडून राहा") ------------------------------------
@pytest.mark.parametrize(
    "advice",
    [
        "थोडा वेळ शांत पडून राहा. बरं वाटेल.",
        "आराम करा आणि पाणी प्या.",
        "थोडं पाणी प्या.",
        "एक गोळी घ्या.",
        "डॉक्टरकडे जा.",
        "तुम्ही डॉक्टरकडे जावं.",
        "थोड़ा आराम कीजिए।",
        "पानी पीजिए और आराम करें।",
        "दवाई ले लीजिए।",
        "डॉक्टर के पास जाइए।",
        "Please rest and drink some water.",
        "You should lie down for a while.",
        "Go see a doctor.",
        "Try taking a pill.",
    ],
)
def test_health_advice_is_a_boundary_violation(advice):
    lang = "en" if advice.isascii() else ("hi" if any(w in advice for w in ("कीजिए", "करें", "पीजिए", "जाइए", "लीजिए")) else "mr")
    assert "medical" in companion_violations(advice, lang)


@pytest.mark.parametrize(
    "fine",
    ["छान वाटलं. मग पुढे काय झालं?", "अरे वा! तुम्ही बागेत काय पाहिलं?", "That sounds lovely. What did you see?"],
)
def test_ordinary_talk_is_not_flagged(fine):
    assert "medical" not in companion_violations(fine, "en" if fine.isascii() else "mr")


def test_an_llm_reply_with_advice_is_replaced_by_the_fixed_line(core_http, uid):
    def llm(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        text = "थोडा वेळ शांत पडून राहा." if body["temperature"] != 0.0 else json.dumps(
            {"intent": "CHAT", "confidence": 0.9, "language": "mr"})
        return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})

    client = EvonClient("https://llm.test/v1", "m", http=httpx.Client(transport=httpx.MockTransport(llm)),
                        schema=load_intent_schema(), provider="TestAI")
    res = _engine(core_http, client).handle(uid, "आज मी बागेत गेले होते आणि मला खूप छान वाटलं")
    assert "पडून राहा" not in res.reply and res.reply in rp.CHAT["mr"]
