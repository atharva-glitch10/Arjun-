"""Close an idle voice session after 60 s (T8): saves speech-recognition credits and the elder's mic.

Spoken closing line first, then the app is told this is a NORMAL end (not a dropped connection), then the
agent leaves. It never closes while anyone is speaking, a yes/no is pending, a safety reply is recent, or a
reminder is waiting; if the elder starts talking during the closing line, the session stays open.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger("arjun.idle")

IDLE_AFTER_S = 60.0


class IdlePolicy:
    def __init__(self, idle_after_s: float = IDLE_AFTER_S, clock: Callable[[], float] = time.monotonic) -> None:
        self.idle_after_s, self.clock = idle_after_s, clock
        self._last = clock()

    def touch(self) -> None:
        self._last = self.clock()

    def idle_for(self) -> float:
        return self.clock() - self._last

    def may_close(self, quiet: bool, busy: dict[str, Any] | None) -> bool:
        if busy is None:  # could not ask reasoning: do not guess
            return False
        blocked = busy.get("pending") or busy.get("safety_hold") or busy.get("queued", 0) > 0
        return self.idle_for() >= self.idle_after_s and quiet and not blocked


class IdleCloser:
    def __init__(
        self,
        policy: IdlePolicy,
        *,
        quiet: Callable[[], bool],
        get_busy: Callable[[], Awaitable[dict[str, Any] | None]],
        say_closing: Callable[[], Awaitable[str]],
        publish_closed: Callable[[], Awaitable[None]],
        shutdown: Callable[[], Awaitable[None]],
        poll_s: float = 5.0,
    ) -> None:
        self.policy, self.quiet, self.get_busy = policy, quiet, get_busy
        self.say_closing, self.publish_closed, self.shutdown = say_closing, publish_closed, shutdown
        self.poll_s = poll_s
        self.closing = False

    async def tick(self) -> bool:
        """True once the session has been closed."""
        if self.closing:
            return True
        if self.policy.idle_for() < self.policy.idle_after_s or not self.quiet():
            return False
        if not self.policy.may_close(True, await self.get_busy()):
            return False
        if await self.say_closing() == "interrupted":  # the elder spoke over the closing line
            self.policy.touch()
            return False
        self.closing = True
        await self.publish_closed()
        await self.shutdown()
        log.info("voice session closed after %.0f s idle", self.policy.idle_after_s)
        return True

    async def run(self) -> None:
        while not self.closing:
            try:
                await self.tick()
            except Exception:  # noqa: BLE001 - a failed check must never end the session by accident
                log.exception("idle check failed")
            await asyncio.sleep(self.poll_s)
