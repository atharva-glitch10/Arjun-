"""The frontend owns the language (2026-11-10): `reply_language` in the /turn body is authoritative. The reply, the fixed lines (safety
included) and the LLM prompt all use it, whatever the utterance, Prisma's label or the profile say. LLM mocked."""

import pytest
from fastapi.testclient import TestClient
from reasoning_svc import langswitch
from reasoning_svc import main as reasoning_main
from reasoning_svc import replies as rp
from reasoning_svc.core_client import CoreClient
from reasoning_svc.langid import classify
from reasoning_svc.turn import TurnEngine
from test_language_switch import WrongThenRight, llm_chat
from test_web_search import NOW, Llm, _understand, make

ALL = ["mr", "hi", "en", "bn", "gu", "kn", "ml", "pa", "ta", "te"]
# a Marathi sentence, spoken with Prisma label mr-IN, in a profile set to Marathi: everything points to Marathi
MARATHI_TEXT = "आज तुम्ही कसे आहात, मला खूप छान वाटतंय"


class _NoLimit:
    def take(self, key):  # the per-user turn limiter is not what these tests are about
        return 0


@pytest.fixture()
def api(core_http, uid, monkeypatch):
    monkeypatch.setattr(reasoning_main, "_turn_bucket", _NoLimit())

    def build(llm):
        eng = make(core_http, llm) if llm is not None else TurnEngine(CoreClient(core_http), evon=None, clock=lambda: NOW, ask_first=False)
        monkeypatch.setattr(reasoning_main, "_engine", eng)
        return TestClient(reasoning_main.app), eng

    return build


def turn(client, uid, text, **body):
    return client.post("/turn", json={"user_id": uid, "text": text, **body})


@pytest.mark.parametrize("lang", ALL)
def test_reply_language_wins_over_utterance_label_and_profile(api, uid, lang):
    client, _ = api(llm_chat("x"))
    r = turn(client, uid, MARATHI_TEXT, language_code="mr-IN", reply_language=lang)
    assert r.status_code == 200 and r.json()["language"] == lang


@pytest.mark.parametrize("lang", ALL)
def test_the_fixed_safety_line_is_in_the_frontend_language(api, uid, lang):
    """Safety logic is untouched; only the language of its fixed template follows the screen."""
    client, _ = api(llm_chat("x"))
    r = turn(client, uid, "मला छातीत दुखतंय", reply_language=lang).json()
    assert r["intent"] == "EMERGENCY" and r["mode"] == "safety" and r["language"] == lang
    assert classify(r["reply"], default=lang).lang == lang, (lang, r["reply"])


@pytest.mark.parametrize("lang", ALL)
def test_other_fixed_lines_follow_it_too(api, uid, lang):
    client, _ = api(None)  # no LLM: the rules answer from the fixed reply tables
    r = turn(client, uid, "आज काय आहे", reply_language=lang).json()  # "what is on today?"
    assert r["language"] == lang and r["reply"] == rp.R[lang]["today_none"]


def test_the_llm_prompt_states_that_language_last(api, uid):
    llm = llm_chat("ठीक है, मैं ठीक हूँ।")
    client, _ = api(llm)
    turn(client, uid, MARATHI_TEXT, language_code="mr-IN", reply_language="hi")
    system = [c[0] for c in llm.calls if "Return ONLY one JSON object" in c[0]][-1]
    assert "REPLY LANGUAGE (final rule): reply ONLY in Hindi (Devanagari script)" in system


def test_a_reply_in_another_language_than_the_screens_is_corrected(api, uid):
    llm = WrongThenRight({**_understand(web=False), "reply": "मी तुमच्याशी हिंदीतच बोलतो.", "answer_mode": "know", "know_confidence": 0.99},
                         ["ठीक है, मैं आपसे हिंदी में ही बात करूंगा।"])
    client, eng = api(llm)
    r = turn(client, uid, MARATHI_TEXT, language_code="mr-IN", reply_language="hi").json()
    assert r["language"] == "hi" and classify(r["reply"]).lang == "hi" and eng.lang_guard["retried"] == 1  # the guard checks against the SCREEN's language


def test_a_switch_request_still_switches_and_confirms_in_the_new_language(api, uid):
    client, _ = api(llm_chat("x"))
    r = turn(client, uid, "मुझसे हिंदी में बात करना", reply_language="mr").json()
    assert r["intent"] == "LANGUAGE_SWITCH" and r["language"] == "hi" and langswitch.NAMES["hi"] in r["reply"]
    assert r["active_language"] == "hi"  # the page follows: its next request carries reply_language=hi


def test_without_the_parameter_nothing_changes(api, uid):
    client, _ = api(llm_chat("ठीक आहे."))
    assert turn(client, uid, "तुम्ही कसे आहात").json()["language"] == "mr"
    assert turn(client, uid, "आप कैसे हैं आज, मैं ठीक हूँ").json()["language"] == "hi"


@pytest.mark.parametrize("bad", ["xx", "MR", "hindi", "", "mr-IN", "<b>", "a" * 40])
def test_an_invalid_reply_language_is_refused(api, uid, bad):
    client, _ = api(llm_chat("x"))
    assert turn(client, uid, "नमस्कार", reply_language=bad).status_code == 422


def test_prepare_uses_it_for_the_filler_and_the_hold_line(api, uid):
    client, _ = api(llm_chat("x"))
    body = client.post("/turn/prepare", json={"user_id": uid, "text": "आज पाऊस पडेल का", "reply_language": "hi"}).json()
    assert body["needs_web"] is True and body["language"] == "hi"
    assert body["filler"] == rp.R["hi"]["web_filler"] and body["hold"] == rp.R["hi"]["web_hold"]


def test_the_engine_takes_the_parameter_directly_too(core_http, uid):
    res = make(core_http, Llm(_understand(web=False))).handle(uid, MARATHI_TEXT, "mr-IN", reply_language="ta")
    assert res.language == "ta"
