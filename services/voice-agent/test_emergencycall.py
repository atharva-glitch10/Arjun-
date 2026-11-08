from types import SimpleNamespace as R

import emergencycall as ec
import httpx


def test_only_the_emergency_intent_escalates():
    assert ec.is_emergency(R(intent="EMERGENCY"))
    assert ec.is_emergency(R(intent="emergency"))
    assert not ec.is_emergency(R(intent="DISTRESS"))
    assert not ec.is_emergency(R(intent="chat"))
    assert not ec.is_emergency(R())


def test_escalate_never_raises(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(ec.httpx, "post", boom)
    assert ec.escalate(1, "help") == {"stage": "help", "placed": 0, "error": "ConnectError"}


def test_spoken_lines_never_promise_help_is_coming():
    for line in (ec.SAID_HELP_CALLED, ec.SAID_NO_CALL):
        assert "येत आहे" not in line and "112" in line
