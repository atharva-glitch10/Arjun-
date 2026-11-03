"""The spoken side of the emergency policy: a physical emergency reaches core-api as an emergency (always alerts),
emotional distress as distress (consent only). The reply is the fixed template either way."""

import pytest

EMERGENCIES = [
    "मला छातीत दुखतंय",  # chest pain
    "मला श्वास घेता येत नाही",  # can't breathe
    "मी आत्ताच पडलो",  # a fall, now
    "मला चक्कर येऊन बेशुद्ध झाल्यासारखं वाटतंय",  # fainting
    "खूप रक्त येतंय",  # bleeding
]


def notes(core_http, uid):
    return [n["kind"] for n in core_http.get(f"/users/{uid}/notifications").json()]


@pytest.mark.parametrize("text", EMERGENCIES)
def test_each_emergency_alerts_the_family_with_consent_off(engine, core_http, uid, text):
    res = engine.handle(uid, text)
    assert res.intent == "EMERGENCY" and res.mode == "safety" and res.screen == "safety"
    assert notes(core_http, uid) == ["emergency"], text


def test_distress_with_consent_off_alerts_nobody(engine, core_http, uid):
    res = engine.handle(uid, "mala jagaychi iccha nahi")
    assert res.intent == "DISTRESS" and res.mode == "safety"
    assert notes(core_http, uid) == []


def test_distress_with_consent_on_alerts_as_distress(engine, core_http, uid):
    core_http.patch(f"/users/{uid}", json={"consent_distress_alert": True})
    engine.handle(uid, "mala jagaychi iccha nahi")
    assert notes(core_http, uid) == ["distress"]


def test_an_emergency_alert_failing_never_silences_the_spoken_reply(core_http, uid):
    from datetime import datetime

    from reasoning_svc.core_client import CoreClient, CoreError
    from reasoning_svc.turn import TurnEngine

    class Flaky(CoreClient):
        def distress(self, uid, kind="distress"):
            raise CoreError(500, "down")

    eng = TurnEngine(Flaky(core_http), None, clock=lambda: datetime(2026, 10, 6, 9, 0))
    res = eng.handle(uid, "मला छातीत दुखतंय")
    assert res.mode == "safety" and "112" in res.reply  # the alert failed: never claim it was sent
    assert "कळवलं" not in res.reply
