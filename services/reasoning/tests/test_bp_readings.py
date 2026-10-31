"""Voice BP readings: repeat the numbers back, store them raw, never judge them.

The acceptance line is "माझा बीपी १३२ बाय ८६" -> a reply containing "१३२ बाय ८६ नोंदवलं" and one
`bp_readings` row. Boundary 7 is checked here: no good / bad / high / low / normal in the reply.
"""

import pytest
from reasoning_svc.readings import format_bp, parse_bp

JUDGEMENT = ("चांगल", "वाईट", "जास्त", "कमी", "normal", "high", "low", "good", "bad", "okay range", "ठीक आहे")


def test_marathi_devanagari_reading_is_parsed():
    assert parse_bp("माझा बीपी १३२ बाय ८६") == (132, 86)
    assert parse_bp("ब्लड प्रेशर १२० वर ८० आहे") == (120, 80)


@pytest.mark.parametrize(
    "text",
    ["बीपी 132/86", "my BP is 132 over 86", "blood pressure 132 by 86", "बीपी १३२ बाय ८६ आहे"],
)
def test_common_ways_of_saying_a_reading(text):
    assert parse_bp(text) == (132, 86)


@pytest.mark.parametrize(
    "text",
    ["माझा बीपी १३२ आहे", "बीपी चांगला आहे", "132 by 86", "मला बीपी माहीत नाही", "उद्या १३२ ला जायचं"],
)
def test_no_reading_is_guessed(text):
    assert parse_bp(text) is None


def test_the_numbers_are_repeated_in_the_elder_s_language():
    assert format_bp(132, 86, "mr") == "१३२ बाय ८६"
    assert format_bp(132, 86, "hi") == "१३२ बाय ८६"
    assert format_bp(132, 86, "en") == "132 over 86"


def test_the_acceptance_reading_is_recorded_and_read_back(core_http, uid, engine):
    res = engine.handle(uid, "माझा बीपी १३२ बाय ८६")
    assert res.intent == "BP_READING"
    assert "१३२ बाय ८६ नोंदवलं" in res.reply
    assert not any(w in res.reply.lower() for w in JUDGEMENT)
    row = core_http.get(f"/users/{uid}/bp-readings").json()[0]
    assert (row["systolic"], row["diastolic"], row["source"]) == (132, 86, "voice")


def test_a_reading_does_not_replace_a_pending_question(core_http, uid, engine):
    engine.handle(uid, "उद्या सकाळी दहा वाजता डॉक्टरकडे जायचं आहे आठवण कर मला")
    pending = core_http.get(f"/users/{uid}/actions/pending").json()
    assert pending is not None
    res = engine.handle(uid, "माझा बीपी १३२ बाय ८६")
    assert res.intent != "BP_READING"
    assert core_http.get(f"/users/{uid}/bp-readings").json() == []
    assert core_http.get(f"/users/{uid}/actions/pending").json()["id"] == pending["id"]
