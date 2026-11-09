"""Found by the end-to-end run of 2026-11-09."""
from reasoning_svc.parser import parse


def test_medicine_decisions_are_medical_questions():
    from datetime import datetime
    now = datetime(2026, 11, 9, 10)
    for t in ("मी गोळी दोनदा घेऊ का?", "काय करू, बीपी गोळी राहिली", "दवाई दुबारा लूँ क्या"):
        assert parse(t, t, now, "mr", False).intent == "MEDICAL_QUESTION", t


def test_chat_without_a_model_is_never_silent(engine, uid):
    res = engine.handle(uid, "आज मी दिवाळीचा फराळ केला")
    assert res.reply and not res.silent


def test_safety_turns_bypass_the_rate_limit(monkeypatch):
    from fastapi.testclient import TestClient
    from reasoning_svc import main

    class Busy:
        def take(self, key):
            return 5.0

    monkeypatch.setattr(main, "_turn_bucket", Busy())
    client = TestClient(main.app)
    assert client.post("/turn", json={"user_id": 1, "text": "गप्पा मारूया"}).status_code == 429
    r = client.post("/turn", json={"user_id": 1, "text": "माझ्या छातीत दुखतंय"})
    assert r.status_code != 429


def test_name_question_gets_the_honest_ai_line(engine, uid):
    res = engine.handle(uid, "तुझं नाव काय?")
    assert "अर्जुन" in res.reply and "एआय" in res.reply


def test_english_time_and_next(engine, uid):
    assert engine.handle(uid, "what is the time?").intent == "TIME_QUERY"
    assert engine.handle(uid, "पुढचं काय आहे?").intent == "NEXT_UP"


def test_college_is_not_a_phone_call(engine, uid):
    res = engine.handle(uid, "माझा मुलगा आर्यन आज कॉलेजला गेला")
    assert "फोन" not in res.reply
