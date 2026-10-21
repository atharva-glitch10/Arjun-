"""Medicine paths: voice can report intake (with a spoken yes), can never create or edit medicines,
and medicine questions are deflected with a fixed template (no medical content)."""

import pytest
from reasoning_svc import replies as rp

MR = rp.R["mr"]
DEFLECTS = {
    text.format(name="Rahul")
    for lang in rp.R.values()
    for key, text in lang.items()
    if key in ("med_deflect", "med_deflect_named")
}


def _add_medicine(core_http, uid, **over):
    body = {"name": "Telma AM", "dose": "1 tablet (as entered)", "anchor": "fixed", "time": "09:00"}
    body.update(over)
    r = core_http.post(f"/users/{uid}/medicines", json=body)
    assert r.status_code == 201
    return r.json()


def _due(core_http, uid):
    return core_http.get(f"/users/{uid}/medicines/due").json()["current"]


def _pending(core_http, uid):
    return core_http.get(f"/users/{uid}/actions/pending").json()


def test_taken_by_voice_needs_spoken_yes_and_quotes_sql_text(engine, core_http, uid):
    _add_medicine(core_http, uid)
    res = engine.handle(uid, "ghetli")
    assert res.intent == "MED_TAKEN" and res.awaiting_confirmation
    assert "Telma AM" in res.reply and "1 tablet (as entered)" in res.reply  # verbatim from SQL
    assert len(_due(core_http, uid)) == 1  # nothing recorded before the yes
    res = engine.handle(uid, "ho")
    assert res.intent == "CONFIRM_YES"
    assert _due(core_http, uid) == []
    history = core_http.get(f"/users/{uid}/medicine-doses").json()
    assert history[0]["status"] == "taken" and history[0]["taken_at"] is not None


def test_taken_in_devanagari_with_medicine_word(engine, core_http, uid):
    _add_medicine(core_http, uid)
    res = engine.handle(uid, "औषध घेतली")
    assert res.intent == "MED_TAKEN" and res.awaiting_confirmation


def test_no_after_taken_prompt_records_nothing(engine, core_http, uid):
    _add_medicine(core_http, uid)
    engine.handle(uid, "ghetli")
    res = engine.handle(uid, "nahi")
    assert res.reply == MR["cancelled"]
    assert len(_due(core_http, uid)) == 1


def test_nothing_due_says_so_and_saves_nothing(engine, core_http, uid):
    _add_medicine(core_http, uid, time="21:00")  # later today
    res = engine.handle(uid, "aushadh ghetli")
    assert res.reply == MR["med_none_due"] and not res.awaiting_confirmation
    assert _pending(core_http, uid) is None


def test_two_due_asks_which_never_guesses(engine, core_http, uid):
    _add_medicine(core_http, uid, name="Telma AM")
    _add_medicine(core_http, uid, name="Homin XY")
    res = engine.handle(uid, "ghetli")
    assert "Telma AM" in res.reply and "Homin XY" in res.reply
    assert not res.awaiting_confirmation and _pending(core_http, uid) is None
    res = engine.handle(uid, "Homin ghetli")
    assert res.awaiting_confirmation and "Homin XY" in res.reply
    engine.handle(uid, "ho")
    assert [d["name"] for d in _due(core_http, uid)] == ["Telma AM"]


def test_snooze_by_voice_after_spoken_yes(engine, core_http, uid):
    _add_medicine(core_http, uid)
    res = engine.handle(uid, "15 minitanni sang")
    assert res.intent == "MED_SNOOZE" and res.awaiting_confirmation
    assert len(_due(core_http, uid)) == 1
    engine.handle(uid, "ho")
    assert _due(core_http, uid) == []  # hidden until the snooze ends


def test_snooze_without_due_medicine_is_harmless(engine, core_http, uid):
    res = engine.handle(uid, "15 minitanni sang")
    assert res.reply == MR["med_none_due"]


# ---- never answer medical questions about medicines ------------------------------------------
QUESTIONS = [
    "aushadh skip kela tar chalel ka",
    "औषध घ्यायला विसरले",
    "goli kashasathi aahe",
    "औषध दोन गोळ्या घेतल्या तर चालेल का",
    "medicine side effects kay aahet",
    "aushadh nako mala",
    "can I take the medicine late",
    "dawa kyun leni hai",
    "औषध घेतली नाही",
    "kiti goli ghyaychi",
]


@pytest.mark.parametrize("text", QUESTIONS)
def test_medicine_questions_are_deflected_not_answered(engine, core_http, uid, text):
    core_http.post(f"/users/{uid}/contacts", json={"name": "Rahul", "relation": "son"})
    _add_medicine(core_http, uid)
    res = engine.handle(uid, text)
    assert res.intent == "MEDICAL_QUESTION"
    assert res.reply in DEFLECTS  # fixed template: no dose advice, no "take"/"skip" instruction
    assert len(_due(core_http, uid)) == 1  # nothing executed
    assert _pending(core_http, uid)["action_type"] == "REQUEST_CAREGIVER"  # only after a yes


def test_deflection_tells_family_only_after_yes(engine, core_http, uid):
    _add_medicine(core_http, uid)
    engine.handle(uid, "औषध घ्यायला विसरले")
    assert core_http.get(f"/users/{uid}/caregiver-requests").json() == []
    engine.handle(uid, "ho")
    assert len(core_http.get(f"/users/{uid}/caregiver-requests").json()) == 1
    assert len(_due(core_http, uid)) == 1  # still not marked taken


# ---- voice can never create or edit medicines -------------------------------------------------
@pytest.mark.parametrize(
    "text", ["udya 10 vajta aushadh remind kar", "ratri 8 vajta goli remind kar", "औषधाची आठवण ठेव"]
)
def test_voice_cannot_create_medicine_reminders(engine, core_http, uid, text):
    res = engine.handle(uid, text)
    assert res.reply == MR["med_family_sets"] and res.awaiting_confirmation
    assert core_http.get(f"/users/{uid}/medicines").json() == []
    assert core_http.get(f"/users/{uid}/reminders").json() == []
    engine.handle(uid, "ho")  # even a yes only notifies the family
    assert core_http.get(f"/users/{uid}/medicines").json() == []
    assert core_http.get(f"/users/{uid}/reminders").json() == []


def test_medicine_word_in_followup_slot_is_refused(engine, core_http, uid):
    engine.handle(uid, "remind kar")  # asks what to remember
    res = engine.handle(uid, "aushadh")
    assert res.reply == MR["med_family_sets"]
    assert core_http.get(f"/users/{uid}/reminders").json() == []


def test_distress_overrides_medicine_talk(engine, core_http, uid):
    _add_medicine(core_http, uid)
    res = engine.handle(uid, "mala jagaychi iccha nahi, aushadh nako")
    assert res.intent == "DISTRESS" and res.mode == "safety"
    assert len(_due(core_http, uid)) == 1
