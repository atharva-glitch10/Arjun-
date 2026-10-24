"""Clock time in spoken words, and the never-guess rule (CLAUDE.md boundary 3).

Regression for the first real-speech test (2026-10-24): Prisma wrote "दहा वाजता" in words, the parser
only read digits, fell back to the wake time and Arjun read back 7:00 for a 10:00 doctor visit.
"""

from datetime import datetime

import pytest
from reasoning_svc import replies as rp
from reasoning_svc.parser import Profile, parse

NOW = datetime(2026, 10, 6, 9, 0)
MR = rp.R["mr"]
DOCTOR = "उद्या सकाळी दहा वाजता डॉक्टरकडे जायचं आहे आठवण कर मला"  # real Prisma transcript


def _draft(text):
    return parse(text, Profile(), NOW, "mr", False).draft


def _pending(core_http, uid):
    return core_http.get(f"/users/{uid}/actions/pending").json()


@pytest.mark.parametrize(
    "text,time",
    [
        (DOCTOR, "10:00"),
        ("उद्या सकाळी दहा वाजता डॉक्टरांकडे जायचं आहे आठवण कर मला", "10:00"),
        ("udya sakali daha vajta doctor la jaycha aahe athvan thev", "10:00"),
        ("कल सुबह दस बजे डॉक्टर के पास जाना है याद दिलाओ", "10:00"),
        ("kal subah das baje doctor jana hai yaad dilao", "10:00"),
        ("उद्या सकाळी अकरा वाजता डॉक्टरकडे जायचं आहे आठवण कर", "11:00"),
        ("उद्या दुपारी दोन वाजता डॉक्टरकडे जायचं आहे आठवण कर", "14:00"),
        ("उद्या संध्याकाळी सहा वाजता डॉक्टरकडे जायचं आहे आठवण कर", "18:00"),
        ("उद्या रात्री नऊ वाजता डॉक्टरकडे जायचं आहे आठवण कर", "21:00"),
        ("उद्या सकाळी साडे दहा वाजता डॉक्टरकडे जायचं आहे आठवण कर", "10:30"),
        ("उद्या सकाळी साडेदहा वाजता डॉक्टरकडे जायचं आहे आठवण कर", "10:30"),
        ("उद्या सकाळी सव्वा दहा वाजता डॉक्टरकडे जायचं आहे आठवण कर", "10:15"),
        ("उद्या सकाळी पावणे दहा वाजता डॉक्टरकडे जायचं आहे आठवण कर", "09:45"),
        ("उद्या दुपारी दीड वाजता डॉक्टरकडे जायचं आहे आठवण कर", "13:30"),
        ("उद्या दुपारी अडीच वाजता डॉक्टरकडे जायचं आहे आठवण कर", "14:30"),
        ("कल सुबह साढ़े दस बजे डॉक्टर के पास जाना है याद दिलाओ", "10:30"),
        ("कल सुबह सवा दस बजे डॉक्टर के पास जाना है याद दिलाओ", "10:15"),
        ("कल सुबह पौने दस बजे डॉक्टर के पास जाना है याद दिलाओ", "09:45"),
        ("kal subah saade das baje doctor jana hai yaad dilao", "10:30"),
        ("उद्या सकाळी दहा डॉक्टरकडे जायचं आहे आठवण कर", "10:00"),  # day-part + hour word, no "वाजता"
    ],
)
def test_hour_words_resolve_to_a_clock_time(text, time):
    d = _draft(text)
    assert d.time == time and d.ambiguous_hour is None
    assert d.date == "2026-10-07"


def test_hour_word_without_a_day_part_asks_am_or_pm():
    d = _draft("उद्या दहा वाजता डॉक्टरकडे जायचं आहे आठवण कर")
    assert d.time is None and d.ambiguous_hour == (10, 0) and d.missing() == "ampm"


def test_hour_words_do_not_end_up_in_the_task_text():
    assert _draft(DOCTOR).task == "डॉक्टरकडे जायचं"
    assert _draft("उद्या सकाळी साडे दहा वाजता डॉक्टरकडे जायचं आहे आठवण कर").task == "डॉक्टरकडे जायचं"
    assert _draft("उद्या सकाळी सव्वा दहा वाजता डॉक्टरकडे जायचं आहे आठवण कर").task == "डॉक्टरकडे जायचं"


def test_number_words_that_are_not_a_clock_time_are_left_alone():
    assert parse("दहा मिनिटांनी सांग", Profile(), NOW, "mr", False).intent == "MED_SNOOZE"
    d = _draft("उद्या दहा मिनिटं चालायला आठवण कर")
    assert d.time is None and d.ambiguous_hour is None and "दहा" in d.task


# ---- never guess ------------------------------------------------------------------------------
def test_live_bug_ten_oclock_is_never_read_back_as_seven(engine, core_http, uid):
    res = engine.handle(uid, DOCTOR)
    assert res.intent == "CREATE_REMINDER" and res.awaiting_confirmation
    assert "10:00" in res.reply and "7:00" not in res.reply
    p = _pending(core_http, uid)
    assert p["payload"]["time"] == "10:00" and p["payload"]["task"] == "डॉक्टरकडे जायचं"


@pytest.mark.parametrize(
    "text",
    [
        "उद्या सकाळी अमुक वाजता डॉक्टरकडे जायचं आहे आठवण कर",
        "udya sakali kahitari vajta doctor la jaycha aahe athvan thev",
        "kal subah pata nahi kitne baje doctor jana hai yaad dilao",
    ],
)
def test_clock_word_without_a_readable_hour_asks_and_never_uses_the_wake_time(engine, core_http, uid, text):
    res = engine.handle(uid, text)
    assert res.intent == "CREATE_REMINDER" and res.awaiting_confirmation
    assert "7:00" not in res.reply
    assert res.reply in (MR["ask_time"], rp.R["hi"]["ask_time"])  # "किती वाजता?"
    assert _pending(core_http, uid) is None  # nothing proposed without a time


def test_clock_word_alone_leaves_the_time_open(engine):
    d = _draft("उद्या सकाळी अमुक वाजता डॉक्टरकडे जायचं आहे आठवण कर")
    assert d.time is None and d.missing() == "time"


def test_day_part_said_earlier_is_remembered_when_the_hour_arrives(engine, core_http, uid):
    engine.handle(uid, "उद्या सकाळी अमुक वाजता डॉक्टरकडे जायचं आहे आठवण कर")
    res = engine.handle(uid, "दहा वाजता")
    assert "10:00" in res.reply and "सकाळी" in res.reply
    assert _pending(core_http, uid)["payload"]["time"] == "10:00"


def test_bare_day_part_with_no_clock_word_still_uses_the_family_set_anchor(engine, core_http, uid):
    # unchanged by the guard: "सकाळी" alone means the configured wake time, no clock word was spoken
    res = engine.handle(uid, "udya sakali doctor la jaycha aahe, remind kar")
    assert "7:00" in res.reply


# ---- readback wording ---------------------------------------------------------------------------
def test_readback_wording(engine, uid):
    res = engine.handle(uid, DOCTOR)
    assert "साठी" not in res.reply
    assert res.reply == "उद्या सकाळी 10:00 वाजता आठवण ठेवू का: डॉक्टरकडे जायचं? हो किंवा नाही सांगा."


def test_readback_wording_in_hindi_and_english():
    assert rp.R["hi"]["confirm_reminder"].format(task="X", when="W") == "W याद दिलाऊँ: X? हाँ या नहीं बताइए।"
    assert rp.R["en"]["confirm_reminder"].format(task="X", when="W") == "Shall I remind you W: X? Please say yes or no."
