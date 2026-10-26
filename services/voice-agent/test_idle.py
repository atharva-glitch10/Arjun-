"""T8 step 3: close an idle voice session after 60 s, with a spoken line first, and NEVER while a safety reply
is recent, a yes/no is pending, something is queued, or anyone is speaking."""

import asyncio

from bridge import CLOSING_REPLY
from idle import IdleCloser, IdlePolicy


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def run(coro):
    return asyncio.run(coro)


FREE = {"pending": False, "safety_hold": False, "queued": 0}


def test_idle_clock_runs_from_the_last_activity():
    c = Clock()
    p = IdlePolicy(60, clock=c)
    c.t = 59
    assert p.idle_for() == 59 and not p.may_close(True, FREE)
    c.t = 60
    assert p.may_close(True, FREE)
    p.touch()
    assert p.idle_for() == 0 and not p.may_close(True, FREE)


def test_never_closes_while_any_blocker_is_true():
    c = Clock()
    p = IdlePolicy(60, clock=c)
    c.t = 600
    assert p.may_close(True, FREE)
    assert not p.may_close(False, FREE)  # someone is speaking / a turn is in flight
    assert not p.may_close(True, {**FREE, "pending": True})  # a yes/no is waiting
    assert not p.may_close(True, {**FREE, "safety_hold": True})  # a safety reply is recent
    assert not p.may_close(True, {**FREE, "queued": 1})  # a reminder is waiting to be spoken
    assert not p.may_close(True, None)  # could not ask: do not guess


def make_closer(c, busy=FREE, say_result="done", quiet=True):
    log = []

    async def get_busy():
        log.append("busy?")
        return busy

    async def say_closing():
        log.append("say")
        return say_result

    async def publish_closed():
        log.append("publish closed")

    async def shutdown():
        log.append("shutdown")

    closer = IdleCloser(
        IdlePolicy(60, clock=c), quiet=lambda: quiet, get_busy=get_busy, say_closing=say_closing,
        publish_closed=publish_closed, shutdown=shutdown, poll_s=0,
    )
    return closer, log


def test_after_60_quiet_seconds_it_says_the_closing_line_then_closes_in_that_order():
    c = Clock()
    closer, log = make_closer(c)
    c.t = 61
    assert run(closer.tick()) is True
    assert log == ["busy?", "say", "publish closed", "shutdown"]


def test_nothing_happens_before_60_seconds_and_nothing_is_even_asked():
    c = Clock()
    closer, log = make_closer(c)
    c.t = 30
    assert run(closer.tick()) is False and log == []


def test_it_does_not_close_while_a_blocker_holds_and_does_not_speak():
    c = Clock()
    for busy in ({**FREE, "pending": True}, {**FREE, "safety_hold": True}, {**FREE, "queued": 2}):
        closer, log = make_closer(c, busy=busy)
        c.t += 100
        assert run(closer.tick()) is False and "say" not in log and "shutdown" not in log


def test_it_does_not_close_while_someone_is_speaking():
    c = Clock()
    closer, log = make_closer(c, quiet=False)
    c.t = 100
    assert run(closer.tick()) is False and log == []


def test_if_the_elder_starts_talking_during_the_closing_line_the_session_stays_open():
    c = Clock()
    closer, log = make_closer(c, say_result="interrupted")
    c.t = 100
    assert run(closer.tick()) is False
    assert "shutdown" not in log and "publish closed" not in log
    assert closer.policy.idle_for() == 0  # the clock starts again


def test_a_failing_busy_lookup_keeps_the_session_open():
    c = Clock()
    closer, log = make_closer(c, busy=None)
    c.t = 100
    assert run(closer.tick()) is False and "say" not in log


def test_it_closes_only_once():
    c = Clock()
    closer, log = make_closer(c)
    c.t = 100
    run(closer.tick())
    run(closer.tick())
    assert log.count("shutdown") == 1


def test_the_closing_line_is_the_approved_wording_and_names_the_talk_button():
    assert CLOSING_REPLY["mr"] == "ठीक आहे. गरज लागली तर 'बोला' दाबा."
    assert all("बोला" in line for line in CLOSING_REPLY.values())
