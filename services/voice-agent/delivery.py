"""Speak queued reminders and medicine prompts in an open voice session (T8).

The queue and the wording live behind reasoning / core-api; this loop only moves one item at a time:
claim -> show its screen -> speak -> report. "spoken" is reported ONLY after playback really completed; an
interruption or a speech failure puts the item back, so nothing is ever called heard when it was not.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger("arjun.delivery")

SPOKEN_RETRIES = 3


class DeliveryLoop:
    def __init__(
        self,
        *,
        claim_next: Callable[[], Awaitable[dict[str, Any] | None]],
        spoken: Callable[[int], Awaitable[None]],
        release: Callable[[int, str], Awaitable[None]],
        speak: Callable[[str], Awaitable[bool]],
        publish: Callable[[dict[str, Any]], Awaitable[None]],
        can_speak: Callable[[], bool],
        poll_s: float = 3.0,
        retry_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.claim_next, self.spoken, self.release = claim_next, spoken, release
        self.speak, self.publish, self.can_speak = speak, publish, can_speak
        self.poll_s, self.retry_sleep = poll_s, retry_sleep

    async def tick(self) -> str:
        """One step. Returns skipped | idle | spoken | spoken_unreported | interrupted | failed."""
        if not self.can_speak():
            return "skipped"
        try:
            item = await self.claim_next()
        except Exception:  # noqa: BLE001 - reasoning down: try again next poll, never crash the session
            log.exception("could not ask for the next delivery")
            return "idle"
        if not item:
            return "idle"
        did = int(item["delivery_id"])
        try:
            await self.publish(item)  # the screen changes as Arjun starts to speak
        except Exception:  # noqa: BLE001 - a screen update must never silence the reminder
            log.exception("could not publish the screen for delivery %s", did)
        try:
            completed = await self.speak(item["text"])
        except Exception:  # noqa: BLE001
            log.exception("speech failed for delivery %s", did)
            await self._release(did, "tts")
            return "failed"
        if not completed:
            await self._release(did, "interrupted")  # the elder started talking: not a failure, try again later
            return "interrupted"
        for attempt in range(SPOKEN_RETRIES):
            try:
                await self.spoken(did)
                log.info("delivery %s spoken", did)
                return "spoken"
            except Exception:  # noqa: BLE001
                log.warning("could not report delivery %s as spoken (attempt %s)", did, attempt + 1)
                await self.retry_sleep(0.5)
        log.error("delivery %s was spoken but never reported; core-api will recycle the claim", did)
        return "spoken_unreported"

    async def _release(self, did: int, reason: str) -> None:
        try:
            await self.release(did, reason)
        except Exception:  # noqa: BLE001 - the sweep recycles a stale claim anyway
            log.exception("could not release delivery %s", did)

    async def run(self) -> None:
        while True:
            await self.tick()
            await asyncio.sleep(self.poll_s)
