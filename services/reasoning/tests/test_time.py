"""Time and day guidance: the household clock + SQL, spoken through fixed templates."""

from reasoning_svc import replies as rp

MR = rp.R["mr"]


def _pending(core_http, uid):
    return core_http.get(f"/users/{uid}/actions/pending").json()


def test_time_query_uses_clock_and_names_what_is_next(engine, core_http, uid):
    res = engine.handle(uid, "kiti vajle")
    assert res.intent == "TIME_QUERY" and not res.awaiting_confirmation
    assert "9:00" in res.reply and "सकाळी" in res.reply
    # next thing today is the family-set lunch time, from the profile (13:00)
    assert "1:00" in res.reply and MR["meal_lunch"] in res.reply
    assert _pending(core_http, uid) is None  # asking the time never proposes anything


def test_time_query_in_english(engine, uid):
    res = engine.handle(uid, "what time is it")
    assert res.intent == "TIME_QUERY"
    assert res.reply.startswith("It is 9:00 in the morning now.")


def test_date_query(engine, uid):
    res = engine.handle(uid, "aaj konta divas aahe")
    assert res.intent == "TIME_QUERY"
    assert "मंगळवार" in res.reply and "6" in res.reply and "ऑक्टोबर" in res.reply


def test_next_up_lists_pending_items_verbatim_then_next(engine, core_http, uid):
    core_http.post(
        f"/users/{uid}/reminders", json={"task": "water plants", "date": "2026-10-06", "time": "09:00"}
    )
    core_http.post(
        f"/users/{uid}/appointments",
        json={"title": "Eye check", "starts_at": "2026-10-06T11:00:00", "location": "Pune"},
    )
    res = engine.handle(uid, "ata kay karaycha")
    assert res.intent == "NEXT_UP"
    assert "water plants" in res.reply  # due and not done
    assert "Eye check" in res.reply  # next ahead (11:00 comes before lunch)


def test_next_up_with_nothing_planned_after_dinner(core_http, uid):
    from datetime import datetime

    from core_api.main import app, get_now
    from reasoning_svc.core_client import CoreClient
    from reasoning_svc.turn import TurnEngine

    late = datetime(2026, 10, 6, 22, 0)
    app.dependency_overrides[get_now] = lambda: late
    eng = TurnEngine(CoreClient(core_http), evon=None, clock=lambda: late)
    res = eng.handle(uid, "what's next")
    assert res.intent == "NEXT_UP" and res.reply == MR["next_none"]  # no language cue -> user default (mr)


def test_due_medicine_is_guided_by_name_and_dose_from_sql(engine, core_http, uid):
    core_http.post(
        f"/users/{uid}/medicines",
        json={"name": "Telma AM", "dose": "1 tablet (as entered)", "anchor": "fixed", "time": "09:00"},
    )
    res = engine.handle(uid, "ata kay karaycha")
    assert "Telma AM, 1 tablet (as entered)" in res.reply


def test_aaj_kay_aahe_now_includes_appointments_and_medicines(engine, core_http, uid):
    core_http.post(
        f"/users/{uid}/appointments",
        json={"title": "Eye check", "starts_at": "2026-10-06T11:00:00", "location": ""},
    )
    res = engine.handle(uid, "aaj kay kay aahe")
    assert res.intent == "LIST_TODAY" and "Eye check" in res.reply


def test_briefing_lists_the_day_with_time_of_day_greeting(engine, core_http, uid):
    core_http.post(
        f"/users/{uid}/appointments",
        json={"title": "Eye check", "starts_at": "2026-10-06T11:00:00", "location": ""},
    )
    text = engine.briefing(uid)
    assert text is not None and text.startswith(MR["greet_morning"])
    assert "Eye check" in text and MR["meal_lunch"] in text


def test_briefing_waits_for_wake_time(engine, core_http, uid):
    core_http.patch(f"/users/{uid}", json={"wake_time": "10:00"})
    assert engine.briefing(uid) is None


def test_briefing_does_not_list_items_already_past(core_http, uid):
    from datetime import datetime

    from core_api.main import app, get_now
    from reasoning_svc.core_client import CoreClient
    from reasoning_svc.turn import TurnEngine

    afternoon = datetime(2026, 10, 6, 16, 0)
    app.dependency_overrides[get_now] = lambda: afternoon
    eng = TurnEngine(CoreClient(core_http), evon=None, clock=lambda: afternoon)
    text = eng.briefing(uid)
    assert text is not None and text.startswith(MR["greet_evening"])
    assert MR["meal_lunch"] not in text  # 13:00 is behind us
    assert MR["meal_dinner"] in text
