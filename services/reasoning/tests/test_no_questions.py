"""The production default (2026-10-31): no "... ठेवू का? हो किंवा नाही". Arjun acts at once, reads back in one
line, and "नको / चुकलं" within the undo window puts it back. Missing details are still asked (never guess)."""

from datetime import datetime, timedelta

NOW = datetime(2026, 10, 6, 9, 0)  # the conftest clock


def _reminders(core_http, uid):
    return core_http.get(f"/users/{uid}/reminders").json()


def test_a_reminder_is_saved_at_once_and_read_back(auto, core_http, uid):
    res = auto.handle(uid, "उद्या सकाळी दहा वाजता डॉक्टरकडे जायची आठवण ठेव")
    assert res.intent == "CREATE_REMINDER" and not res.awaiting_confirmation and res.screen == "saved"
    assert res.reply.startswith("ठेवली: उद्या") and "10" in res.reply  # read back from the saved values
    assert "हो किंवा नाही" not in res.reply and "का?" not in res.reply
    rows = _reminders(core_http, uid)
    assert len(rows) == 1 and rows[0]["due_at"].startswith("2026-10-07T10:00")


def test_nako_right_after_undoes_it(auto, core_http, uid):
    auto.handle(uid, "उद्या सकाळी दहा वाजता डॉक्टरकडे जायची आठवण ठेव")
    res = auto.handle(uid, "नको")
    assert res.reply.startswith("ठीक आहे") and "रद्द" in res.reply
    assert _reminders(core_http, uid) == []


def test_a_correction_replaces_the_one_just_saved(auto, core_http, uid):
    auto.handle(uid, "उद्या सकाळी दहा वाजता डॉक्टरकडे जायची आठवण ठेव")
    auto.handle(uid, "नाही, उद्या सकाळी अकरा वाजता डॉक्टरकडे जायची आठवण ठेव")
    rows = _reminders(core_http, uid)
    assert len(rows) == 1 and rows[0]["due_at"].startswith("2026-10-07T11:00")


def test_after_the_window_nako_is_a_topic_decline_not_an_undo(core_http, uid):
    from reasoning_svc.core_client import CoreClient
    from reasoning_svc.turn import TurnEngine

    t = [0.0]
    eng = TurnEngine(CoreClient(core_http), None, clock=lambda: NOW, ask_first=False, mono=lambda: t[0])
    eng.handle(uid, "उद्या सकाळी दहा वाजता डॉक्टरकडे जायची आठवण ठेव")
    t[0] = 10_000.0
    eng.handle(uid, "नको")
    assert len(_reminders(core_http, uid)) == 1


def test_missing_details_are_still_asked_never_guessed(auto, core_http, uid):
    res = auto.handle(uid, "डॉक्टरकडे जायची आठवण ठेव")
    assert res.awaiting_confirmation  # "कोणत्या दिवशी?" - a question about a missing slot, not a yes/no
    assert _reminders(core_http, uid) == []


def test_help_is_sent_at_once_and_says_where(auto, core_http, uid):
    res = auto.handle(uid, "मला मदत हवी आहे")
    assert res.intent == "REQUEST_CAREGIVER" and not res.awaiting_confirmation
    assert "स्क्रीनवर" in res.reply  # honest: a dashboard note, not a phone call
    kinds = [n["kind"] for n in core_http.get(f"/users/{uid}/notifications").json()]
    assert "caregiver_request" in kinds


def test_yes_after_a_saved_action_is_just_ok(auto, uid):
    auto.handle(uid, "उद्या सकाळी दहा वाजता डॉक्टरकडे जायची आठवण ठेव")
    assert auto.handle(uid, "हो").reply == "ठीक आहे."


def test_a_long_story_is_kept_privately_without_asking(auto, core_http, uid):
    story = "माझ्या लहानपणी आम्ही गावाला जायचो तिथे आजीच्या घरी मोठं अंगण होतं आणि आम्ही सगळे भावंडं खेळायचो"
    res = auto.handle(uid, story)
    assert res.intent == "CHAT" and not res.awaiting_confirmation
    assert core_http.get(f"/users/{uid}/memory-book").json() == []  # private: the family does not see it


def _due_medicine(core_http, uid):
    core_http.post(
        f"/users/{uid}/medicines",
        json={"name": "BP गोळी", "dose": "1 गोळी", "anchor": "fixed", "time": "09:00"},
    )
    return core_http.get(f"/users/{uid}/medicines/due").json()["current"][0]


def test_ghetli_records_a_due_medicine_at_once(auto, core_http, uid):
    dose = _due_medicine(core_http, uid)
    res = auto.handle(uid, "गोळी घेतली")
    assert "नोंदवलं" in res.reply and not res.awaiting_confirmation
    doses = core_http.get(f"/users/{uid}/medicine-doses").json()
    assert [d["status"] for d in doses if d["id"] == dose["id"]] == ["taken"]


def test_ho_right_after_a_medicine_prompt_counts_as_taken(auto, core_http, uid):
    from core_api.main import app as core_app
    from core_api.main import get_now

    dose = _due_medicine(core_http, uid)
    core_app.dependency_overrides[get_now] = lambda: NOW + timedelta(minutes=1)
    core_http.post("/internal/medicines/tick")
    item = auto.deliver_next(uid, "S")
    assert item is not None and item["kind"] == "medicine" and not item["awaiting_confirmation"]
    assert "घेतली का" not in item["text"]
    auto.handle(uid, "हो")
    doses = core_http.get(f"/users/{uid}/medicine-doses").json()
    assert [d["status"] for d in doses if d["id"] == dose["id"]] == ["taken"]


def test_safety_still_overrides_everything(auto, uid):
    auto.handle(uid, "उद्या सकाळी दहा वाजता डॉक्टरकडे जायची आठवण ठेव")
    res = auto.handle(uid, "छातीत दुखतंय")
    assert res.intent == "EMERGENCY" and res.mode == "safety"


def test_prisma_transcribe_with_native_numerals_is_read(auto, core_http, uid):
    """GNANI_STT_FORMAT=transcribe + itn_native_numerals: Prisma writes "१०:३०" instead of "साडेदहा"."""
    res = auto.handle(uid, "उद्या सकाळी १०:३० वाजता डॉक्टरकडे जायची आठवण ठेव")
    assert res.screen == "saved"
    assert _reminders(core_http, uid)[0]["due_at"].startswith("2026-10-07T10:30")


def test_a_core_api_error_does_not_leave_a_draft_that_swallows_the_next_sentence(auto, uid, monkeypatch):
    from reasoning_svc.core_client import CoreError

    def broken(*a, **k):
        raise CoreError(409, "action already expired")

    monkeypatch.setattr(auto.core, "confirm", broken)
    assert "अडचण" in auto.handle(uid, "उद्या सकाळी दहा वाजता डॉक्टरकडे जायची आठवण ठेव").reply
    assert auto.handle(uid, "मला खूप एकटं वाटतंय").intent == "LONELY"
