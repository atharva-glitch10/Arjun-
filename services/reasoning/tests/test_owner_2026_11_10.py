"""Owner decisions of 2026-11-10: medicines guided from her list, minimal self-care, reply in her language."""
from reasoning_svc.turn import _reply_language, is_med_list_question


def test_medicine_list_from_sql(engine, core_http, uid):
    core_http.post(f"/users/{uid}/medicines", json={"name": "बीपीची गोळी", "dose": "1 गोळी", "anchor": "fixed", "time": "21:00"})
    res = engine.handle(uid, "माझी औषधं कोणती आहेत?")
    assert res.intent == "MED_LIST" and "बीपीची गोळी" in res.reply and "1 गोळी" in res.reply


def test_dose_changes_are_still_not_answered():
    assert not is_med_list_question("मी गोळी दोनदा घेऊ का?")
    assert not is_med_list_question("ही गोळी कशासाठी आहे?")
    assert is_med_list_question("आता कोणती गोळी घ्यायची?")


def test_self_care_line_for_a_cut(engine, uid):
    res = engine.handle(uid, "हाताला थोडं कापलं, काय करू?")
    assert res.intent == "SYMPTOM" and "पट्टी" in res.reply and "डॉक्टर" in res.reply


def test_reply_follows_the_spoken_language():
    assert _reply_language("mr-IN", "मैं आज बाजार गई थी", "mr") == "hi"
    assert _reply_language("hi-IN", "आज मी बाजारात गेले होते", "mr") == "mr"
    assert _reply_language("en-IN", "I went to the temple today", "mr") == "en"
    assert _reply_language(None, "I went to the temple today", "mr") == "en"  # no label: the English words decide
    assert _reply_language("mr-IN", "tu manus aahes ka", "mr") == "mr"
