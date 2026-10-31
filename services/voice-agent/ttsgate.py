"""One Timbre request at a time (task E, 2026-10-31).

Gnani's TTS API answers a second concurrent request with 429 RATE_LIMITED ("Only 1 active request is allowed at a time").
Live, that dropped a whole reply: no audio, no "speaking" state, and the turn log showed a reply that was never heard.
LiveKit sends each sentence as its own request and may start the next while the previous one is still downloading, and an
interrupted request can still be active on Gnani's side for a moment. So requests are serialised in this process, and a
busy answer is retried a couple of times after a short wait. Pure (the sleep is injected), so it is tested.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


class TtsGate:
    def __init__(
        self,
        retries: int = 2,
        delay_s: float = 0.4,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.retries, self.delay_s, self._sleep = retries, delay_s, sleep
        self._lock = asyncio.Lock()

    async def run(self, call: Callable[[], Awaitable[T]], is_busy: Callable[[Exception], bool]) -> T:
        """Run `call` alone. If it fails with a "busy" error, wait and try again (at most `retries` times)."""
        async with self._lock:
            attempt = 0
            while True:
                try:
                    return await call()
                except Exception as exc:  # noqa: BLE001 - only the busy kind is retried, everything else is re-raised
                    if not is_busy(exc) or attempt >= self.retries:
                        raise
                    attempt += 1
                    await self._sleep(self.delay_s)
