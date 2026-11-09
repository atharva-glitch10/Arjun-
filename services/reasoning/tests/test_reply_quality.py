"""Reply quality (2026-11-02): short, listening, no guessing, no advice, no filler openers. Built from the 22:47 live
transcripts (synthetic data only). Lexicons are UNVERIFIED until a native speaker reviews them."""

import json
from datetime import datetime

import httpx
import pytest
from reasoning_svc import config
from reasoning_svc.core_client import CoreClient
from reasoning_svc.distress import is_emergency, symptom_category
from reasoning_svc.evon import (
    EvonClient,
    companion_violations,
    load_intent_schema,
    sanitize_companion,
    strip_filler,
    strip_filler_voiced,
)
from reasoning_svc.turn import TurnEngine

NOW = datetime(2026, 10, 6, 9, 0)
STORY = "आज मी बागेत गेले होते आणि मला खूप छान वाटलं"


# ---- strip_filler ------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("वा, छान!", "छान!"),
        ("मला वाटतं, चिकन छान झालं.", "चिकन छान झालं."),
        ("मला समजलं. अरेरे, मग?", "मग?"),  # repeated, from the start only
        ("अरे वा! गाणं कोणतं?", "गाणं कोणतं?"),
        ("हो, ठीक आहे, बरं. सांगा", "सांगा"),
        ("मला आनंद झाला की तुम्ही बोललात", "की तुम्ही बोललात"),
        ("मुझे लगता है आप ठीक हैं", "आप ठीक हैं"),
        ("Oh, wow! I think so", "so"),
        ("okay. Sure, go on", "go on"),
        # not a filler: the word only STARTS with one (the lookahead, not \b, decides)
        ("वाटतं छान", "वाटतं छान"),
        ("वाचन कोणतं आवडतं?", "वाचन कोणतं आवडतं?"),
        ("होळी कशी साजरी केली?", "होळी कशी साजरी केली?"),
        ("okay-dokey", "dokey"),  # "-" is a separator, so this one is stripped
        ("Okayama is a city", "Okayama is a city"),
        # only from the start
        ("चिकन छान झालं, वा!", "चिकन छान झालं, वा!"),
    ],
)
def test_strip_filler(raw, expected):
    assert strip_filler(raw) == expected


def test_strip_filler_voiced_keeps_the_tag():
    assert strip_filler_voiced("<laugh> वा, छान!") == "<laugh> छान!"
    assert strip_filler_voiced("<slow> <pauses> मला वाटतं, हो. सांगा") == "<slow> <pauses> सांगा"
    assert strip_filler_voiced("छान") == "छान"


def test_sanitize_strips_first_and_an_all_filler_reply_is_empty():
    assert sanitize_companion("मला वाटतं, चिकन छान झालं. कोणी बनवलं?", "mr") == ("चिकन छान झालं. कोणी बनवलं?", [])
    assert sanitize_companion("अरेरे", "mr") == (None, ["empty"])
    assert sanitize_companion("वा, हो.", "mr") == (None, ["empty"])


def test_a_long_reply_is_not_rejected_by_character_count_alone():
    long_reply = "तुम्ही आज बागेत गेला होतात हे ऐकून " * 12
    assert len(long_reply) > 300
    assert companion_violations(long_reply, "mr") == []
    assert companion_violations("चिकन छान झालं! कोणी बनवलं?", "mr") == []


# ---- advice is a violation -----------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "advice",
    [
        "डोक्याला त्रास होत असेल तर थोडा वेळ शांत पडून राहा",
        "आराम करा", "पाणी प्या", "डॉक्टरकडे जा", "दवाखान्यात जा", "झोप घ्या",
        "आराम कीजिए", "पानी पीजिए",
        "Please take rest", "lie down for a while", "drink water", "you should see a doctor",
    ],
)
def test_advice_replies_are_rejected(advice):
    assert "medical" in companion_violations(advice, "mr" if any("ऀ" <= c <= "ॿ" for c in advice) else "en")


@pytest.mark.parametrize("fine", ["गाणं कोणतं शिकलात आज?", "घरच्यांना कळवलं आहे.", "हे डॉक्टरांना विचारा."])
def test_good_replies_are_not_flagged(fine):
    assert companion_violations(fine, "mr") == []


# ---- the engine -------------------------------------------------------------------------------------------------
class Llm:
    def __init__(self, content):
        self.content, self.calls = content, []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": self.content}}]})


def engine(core_http, content):
    llm = Llm(content)
    client = EvonClient("https://llm.test/v1", "m", http=httpx.Client(transport=httpx.MockTransport(llm)),
                        schema=load_intent_schema(), provider="TestAI")
    return TurnEngine(CoreClient(core_http), client, clock=lambda: NOW, ask_first=False), llm


def test_the_screen_and_the_voice_lose_the_same_filler(core_http, uid):
    eng, llm = engine(core_http, "<laugh> मला वाटतं, चिकन छान झालं! कोणी बनवलं?")
    res = eng.handle(uid, STORY)
    assert res.reply == "चिकन छान झालं! कोणी बनवलं?"
    assert res.speech == "<laugh> चिकन छान झालं! कोणी बनवलं?"
    assert llm.calls[-1]["max_tokens"] == 700 and llm.calls[-1]["temperature"] == config.COMPANION_TEMPERATURE == 0.5


def test_a_reply_that_is_only_filler_becomes_the_fixed_line(core_http, uid):
    eng, _ = engine(core_http, "अरेरे")
    res = eng.handle(uid, STORY)
    assert res.intent == "CHAT" and res.source != "llm"
    assert res.reply and "अरेरे" not in res.reply


def test_an_advice_reply_from_the_llm_is_replaced(core_http, uid):
    eng, _ = engine(core_http, "डोक्याला त्रास होत असेल तर थोडा वेळ शांत पडून राहा")
    res = eng.handle(uid, STORY)
    assert "पडून" not in res.reply and res.source != "llm"


def test_the_prompt_has_the_companion_contract_and_keeps_tags_and_interests(core_http, uid):
    eng, llm = engine(core_http, "छान!")
    core_http.patch(f"/users/{uid}", json={"interests": ["भजन"]})
    eng.handle(uid, STORY)
    system = llm.calls[0]["messages"][0]["content"]
    for needle in ("NEVER ACT DUMB", "ALWAYS TRY TO GIVE A SOLUTION", "सांगतो", "विचारतो", "करतो", "तुम्ही",
                   "USER CONTEXT", "<laugh>", "भजन", "1-2 short sentences"):
        assert needle in system, needle
    for banned in ("आता कसं वाटतंय?", "हे अजून मला जमत नाही", "at most 12 words", "मला वाटतं"):
        assert banned not in system


# ---- symptoms (new words, UNVERIFIED) ------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    ["सर्दी झाली आहे", "माझं डोकं जड आहे", "I have a cough", "खोकला आहे", "ताप आलाय", "ताप आहे", "बुखार है",
     "नींद नहीं आती", "तबीयत ठीक नहीं है", "I have a headache", "I have a fever", "I am not feeling well",
     "I can't sleep", "मळमळ होतेय", "उलटी झाली", "अशक्तपणा वाटतो", "बरं वाटत नाही", "डोकं दुखतं", "गुडघे दुखतात"],
)
def test_symptom_phrases_are_recognised_and_are_not_emergencies(text):
    assert symptom_category(text) is not None, text
    assert not is_emergency(text)


@pytest.mark.parametrize("text", ["आज डोकं दुखत नाही", "डोकं दुखतं नाही", "पोट दुखत नाही आज", "आज छान दिवस होता"])
def test_a_negated_pain_is_not_a_symptom(text):
    assert symptom_category(text) is None


def test_the_symptom_reply_is_fixed_and_still_makes_one_understanding_call(core_http, uid):
    eng, llm = engine(core_http, "छान!")
    res = eng.handle(uid, "सर्दी झाली आहे")
    assert res.intent == "SYMPTOM" and res.mode == "companion" and len(llm.calls) == 1
    assert "Raw transcript: सर्दी झाली आहे" in llm.calls[0]["messages"][-1]["content"]
    assert res.reply == "हे घरच्यांना किंवा डॉक्टरांना नक्की सांगा."  # no consent: no claim to have told them
    core_http.patch(f"/users/{uid}", json={"consent_distress_alert": True})
    told = eng.handle(uid, "ताप आलाय")
    assert told.reply == "घरच्यांना कळवलं आहे."
    after = eng.handle(uid, STORY)  # the chat continues, and the LLM is asked again for this turn
    assert after.intent == "CHAT" and len(llm.calls) == 3
