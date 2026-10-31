"""Timbre allows ONE active request at a time (live 2026-10-31: 429 RATE_LIMITED "Only 1 active request is allowed at a
time", and that reply was never spoken). The gate serialises synthesis in this process and retries a busy answer."""

import asyncio

import pytest
from ttsgate import TtsGate


class Busy(Exception):
    pass


def busy(exc: Exception) -> bool:
    return isinstance(exc, Busy)


def run(coro):
    return asyncio.run(coro)


def test_two_requests_never_overlap():
    gate = TtsGate(sleep=lambda s: asyncio.sleep(0))
    active, peak = [0], [0]

    async def call():
        active[0] += 1
        peak[0] = max(peak[0], active[0])
        await asyncio.sleep(0.01)
        active[0] -= 1
        return "ok"

    async def main():
        return await asyncio.gather(*(gate.run(call, busy) for _ in range(5)))

    assert run(main()) == ["ok"] * 5
    assert peak[0] == 1


def test_a_busy_answer_is_retried_after_a_short_wait():
    waits = []

    async def fake_sleep(s):
        waits.append(s)

    gate = TtsGate(retries=2, delay_s=0.4, sleep=fake_sleep)
    answers = [Busy("429"), "audio"]

    async def call():
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    assert run(gate.run(call, busy)) == "audio"
    assert waits == [0.4]


def test_it_gives_up_after_the_retries_and_raises_the_busy_error():
    async def fake_sleep(s):
        return None

    gate = TtsGate(retries=2, delay_s=0.1, sleep=fake_sleep)
    calls = [0]

    async def call():
        calls[0] += 1
        raise Busy("429")

    with pytest.raises(Busy):
        run(gate.run(call, busy))
    assert calls[0] == 3  # the first try + 2 retries


def test_another_error_is_not_retried():
    gate = TtsGate(sleep=lambda s: asyncio.sleep(0))
    calls = [0]

    async def call():
        calls[0] += 1
        raise ValueError("bad voice")

    with pytest.raises(ValueError):
        run(gate.run(call, busy))
    assert calls[0] == 1


def test_a_failed_request_releases_the_gate_for_the_next():
    gate = TtsGate(retries=0, sleep=lambda s: asyncio.sleep(0))

    async def bad():
        raise ValueError("x")

    async def good():
        return "fine"

    async def main():
        with pytest.raises(ValueError):
            await gate.run(bad, busy)
        return await gate.run(good, busy)

    assert run(main()) == "fine"
