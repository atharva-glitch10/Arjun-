"""Which Ghar screen a reply belongs on (T6). Reasoning decides it, so it is tested here, not in the app."""

from datetime import datetime

import pytest
from reasoning_svc.main import TurnOut

NOW = datetime(2026, 10, 6, 9, 0)

DOCTOR = "उद्या सकाळी दहा वाजता डॉक्टरकडे जायचं आहे आठवण कर मला"


def _pending(core_http, uid):
    return core_http.get(f"/users/{uid}/actions/pending").json()


def test_turn_out_carries_the_screen(engine, uid):
    res = engine.handle(uid, DOCTOR)
    assert "screen" in TurnOut.model_fields
    assert TurnOut(**res.__dict__).screen == "confirm"


@pytest.mark.parametrize(
    "text,screen",
    [
        (DOCTOR, "confirm"),  # asks yes/no
        ("आज काय आहे", "reply"),
        ("हॅलो", "reply"),
        ("ऐकू येतंय का", "reply"),
        ("मला छातीत दुखतंय", "safety"),  # emergency
        ("mala jagaychi iccha nahi", "safety"),  # distress
    ],
)
def test_screen_for_each_kind_of_reply(engine, uid, text, screen):
    assert engine.handle(uid, text).screen == screen


def test_a_confirmed_action_lands_on_saved_and_a_refused_one_does_not(engine, uid):
    engine.handle(uid, DOCTOR)
    assert engine.handle(uid, "हो").screen == "saved"
    engine.handle(uid, DOCTOR)
    assert engine.handle(uid, "नको").screen == "reply"


def test_a_yes_with_nothing_pending_is_not_saved(engine, uid):
    res = engine.handle(uid, "हो")
    assert res.screen == "reply"


def test_a_safety_screen_follows_even_with_a_confirmation_pending(engine, core_http, uid):
    engine.handle(uid, DOCTOR)  # a yes/no is pending, screen would be "confirm"
    res = engine.handle(uid, "मला छातीत दुखतंय")
    assert res.screen == "safety" and _pending(core_http, uid) is None


# ---- a tapped हो/नको is the same turn as a spoken one ------------------------------------------
@pytest.mark.parametrize("tapped,spoken", [("हो", "हो हो ठेव हो"), ("नको", "नाही नको")])
def test_tap_and_voice_answers_give_the_same_result(core_http, tapped, spoken):
    from reasoning_svc.core_client import CoreClient
    from reasoning_svc.turn import TurnEngine
    outcomes = []
    for answer in (tapped, spoken):
        uid = core_http.post("/users", json={"name": "Aaji (synthetic)", "language": "mr"}).json()["id"]
        e = TurnEngine(CoreClient(core_http), evon=None, clock=lambda: NOW)
        e.handle(uid, DOCTOR)
        res = e.handle(uid, answer)
        saved = core_http.get(f"/users/{uid}/reminders").json()
        outcomes.append((res.intent, res.reply, res.screen, res.mode, len(saved), _pending(core_http, uid)))
    assert outcomes[0] == outcomes[1]


def test_a_tapped_yes_with_nothing_pending_is_refused_like_a_spoken_one(core_http):
    from reasoning_svc.core_client import CoreClient
    from reasoning_svc.turn import TurnEngine
    results = []
    for answer in ("हो", "हो हो"):
        uid = core_http.post("/users", json={"name": "Aaji (synthetic)", "language": "mr"}).json()["id"]
        res = TurnEngine(CoreClient(core_http), evon=None, clock=lambda: NOW).handle(uid, answer)
        results.append((res.reply, res.screen, core_http.get(f"/users/{uid}/reminders").json()))
    assert results[0] == results[1] and results[0][2] == []
