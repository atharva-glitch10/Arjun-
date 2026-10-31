"""Loneliness: a warm fixed reply that points to family, then keep listening. Not a safety override.

The lexicon is UNVERIFIED (no native speaker, no real Prisma output); these tests pin the behaviour only.
"""

import pytest
from reasoning_svc.distress import is_distress, is_emergency, is_lonely


@pytest.mark.parametrize(
    "text",
    ["मला एकटं वाटतं", "मला खूप एकटं वाटतंय", "आज कोणी बोलत नाही माझ्याशी", "mala ekta vatta",
     "मुझे अकेलापन लगता है", "मैं अकेली हूँ", "akela mehsoos hota hai", "I feel so lonely today",
     "nobody talks to me anymore"],
)
def test_lonely_phrases(text):
    assert is_lonely(text)
    assert not is_distress(text) and not is_emergency(text)  # a gentle reply, not a crisis template


@pytest.mark.parametrize(
    "text",
    ["लहानपणी मी एकटी होते", "मला एकटं नाही वाटत", "मैं अकेले बाज़ार जाऊँगी", "उद्या दहा वाजता डॉक्टरकडे जायचं आहे",
     "I like to walk alone in the morning"],
)
def test_not_lonely(text):
    assert not is_lonely(text)


def _contact(core_http, uid, name, rel):
    core_http.post(f"/users/{uid}/contacts", json={"name": name, "relation": rel, "phone": "00000 00001"})


def test_reply_names_the_family_and_keeps_listening(engine, core_http, uid):
    _contact(core_http, uid, "राहुल", "मुलगा")
    _contact(core_http, uid, "नेहा", "नात")
    res = engine.handle(uid, "मला खूप एकटं वाटतंय")
    assert res.intent == "LONELY" and res.mode == "companion" and res.screen == "story"
    assert "राहुल" in res.reply and "नेहा" in res.reply
    assert not res.awaiting_confirmation
    for banned in ("आठवण आली", "मला पण", "मलाही"):  # no "I missed you", no feelings claimed by Arjun
        assert banned not in res.reply


def test_reply_without_contacts_still_points_to_family(engine, uid):
    res = engine.handle(uid, "मला एकटं वाटतं")
    assert res.intent == "LONELY" and "घरच्यांना" in res.reply


def test_family_told_only_with_consent_and_once_a_day(engine, core_http, uid):
    engine.handle(uid, "मला एकटं वाटतं")
    assert not [n for n in core_http.get(f"/users/{uid}/notifications").json() if n["kind"] == "lonely"]
    core_http.patch(f"/users/{uid}", json={"consent_distress_alert": True})
    engine.handle(uid, "मला एकटं वाटतं")
    engine.handle(uid, "आज कोणी बोलत नाही")
    told = [n for n in core_http.get(f"/users/{uid}/notifications").json() if n["kind"] == "lonely"]
    assert len(told) == 1
    assert "एकटं" not in told[0]["body"] and "lonely" in told[0]["body"]  # the fact, never her words


def test_a_pending_question_still_wins(engine, core_http, uid):
    first = engine.handle(uid, "उद्या सकाळी दहा वाजता डॉक्टरकडे जायची आठवण ठेव")
    assert first.awaiting_confirmation
    res = engine.handle(uid, "मला एकटं वाटतं")
    assert res.intent == "PENDING_REPEAT" and res.awaiting_confirmation


def test_distress_still_overrides_loneliness(engine, uid):
    res = engine.handle(uid, "मला एकटं वाटतं, मला मरायचं आहे")
    assert res.intent == "DISTRESS" and res.mode == "safety"
