"""No turn may crash for ANY of the ten languages (2026-11-10: a KeyError in app_replies.A took down every app / media turn
for bn gu kn ml pa ta te when the frontend language was sent as reply_language). The rules path, no LLM."""

import json
from pathlib import Path

import pytest
from reasoning_svc.core_client import CoreClient
from reasoning_svc.turn import TurnEngine
from test_web_search import NOW

ROOT = Path(__file__).resolve().parents[3]
CASES = [json.loads(x)["text"] for x in (ROOT / "eval" / "cases.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
EXTRA = [
    "भजन लाव", "यूट्यूब उघड", "बातम्या सांगा", "राहुलला फोन लाव", "आज पाऊस पडेल का", "सोन्याचा भाव किती", "व्हॉट्सॲप उघड", "गाणं बदल", "थांबव", "आवाज कमी कर",
    "आज काय आहे", "उद्या डॉक्टर", "औषध घेतलं", "मला एकटं वाटतंय", "मला छातीत दुखतंय", "मुझसे हिंदी में बात करना", "speak English", "नमस्कार", "हो", "नाही",
    "call my son", "play a bhajan", "what is the news", "remind me tomorrow at 10 to call Rahul", "मला जगावंसं वाटत नाही", "tell me a story", "आणखी सांग",
]
LANGS = ["mr", "hi", "en", "bn", "gu", "kn", "ml", "pa", "ta", "te"]


@pytest.mark.parametrize("lang", LANGS)
def test_no_turn_crashes_in_any_language(core_http, uid, lang):
    core_http.post(f"/users/{uid}/contacts", json={"name": "Rahul", "relation": "son", "phone": "00000 00000"})
    eng = TurnEngine(CoreClient(core_http), evon=None, clock=lambda: NOW, ask_first=False)
    for text in CASES + EXTRA:
        res = eng.handle(uid, text, reply_language=lang)
        assert isinstance(res.reply, str), (lang, text)
