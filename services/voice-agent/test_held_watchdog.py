"""A held sentence ("नमस्कार अर्जुन" + speech that never becomes words) must still be answered (laptop, 2026-11-08)."""

import asyncio
import contextlib
import logging


def _arjun(monkeypatch):
    for name in ("GNANI_API_KEY", "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
        monkeypatch.setenv(name, "test")
    import agent

    monkeypatch.setattr(agent, "HELD_ANSWER_S", 0.05)
    answered = []

    class Responder:
        async def respond(self, text, source):
            answered.append((text, source))

    class State:
        @contextlib.asynccontextmanager
        async def turn(self):
            yield

    class Policy:
        def touch(self):
            pass

    class Hold:
        held = ""

    a = agent.Arjun.__new__(agent.Arjun)
    a.responder, a.state, a.policy, a.hold = Responder(), State(), Policy(), Hold()
    return a, answered


def test_held_text_is_answered_when_no_more_words_arrive(monkeypatch):
    a, answered = _arjun(monkeypatch)
    a.hold.held = "नमस्कार अर्जुन"
    asyncio.run(a._answer_held_later("नमस्कार अर्जुन"))
    assert answered == [("नमस्कार अर्जुन", "voice")] and a.hold.held == ""


def test_not_answered_twice_when_a_later_turn_took_it(monkeypatch):
    a, answered = _arjun(monkeypatch)
    a.hold.held = ""  # the next turn already combined and answered it
    asyncio.run(a._answer_held_later("नमस्कार अर्जुन"))
    a.hold.held = "नमस्कार अर्जुन आज"  # or replaced it with a longer held part (its own timer answers that)
    asyncio.run(a._answer_held_later("नमस्कार अर्जुन"))
    assert answered == []


def test_second_dispatched_room_logs_both_room_ids(monkeypatch, caplog):
    _arjun(monkeypatch)
    import agent

    monkeypatch.setattr(agent, "_active_rooms", set())
    agent._register_active_room("room-one")
    with caplog.at_level(logging.WARNING, logger="arjun.agent"):
        agent._register_active_room("room-two")
    assert "active_room=room-one dispatched_room=room-two" in caplog.text
    agent._unregister_active_room("room-one")
    agent._unregister_active_room("room-two")
