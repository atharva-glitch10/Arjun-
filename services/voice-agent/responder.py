"""The ONE place a user turn becomes a spoken reply, whether it was spoken or tapped.

A tapped "हो" / "नको" is sent to the agent as text and goes through exactly the same steps as a spoken
one: reasoning (which checks the pending action), the stale / safety / confirmation rules in
`bridge.should_speak`, the screen attributes, then speech. There is no second path to keep in step.
"""

import logging
import time
from collections.abc import Awaitable, Callable

from bridge import BridgeReply, should_speak
from turnlog import TurnLog

logger = logging.getLogger("arjun.responder")


class Responder:
    def __init__(
        self,
        turns: TurnLog,
        ask: Callable[[str], Awaitable[BridgeReply]],
        say: Callable[[str], Awaitable[None]],
        publish: Callable[[BridgeReply, int], Awaitable[None]],
        fallback_text: Callable[[], str],
        thinking: Callable[[bool], Awaitable[None]] | None = None,
        speakable: Callable[[BridgeReply], str] | None = None,
        on_mode: Callable[[str], None] | None = None,
    ) -> None:
        self.turns, self.ask, self.say, self.publish, self.fallback_text = turns, ask, say, publish, fallback_text
        self.thinking = thinking  # the "विचार करतोय…" marker on the elder screen
        # reply -> the exact text for TTS (tagged for Timbre v3, plain otherwise); default: the screen text
        self.speakable = speakable or (lambda r: r.text)
        self.on_mode = on_mode  # the mode of each reply (care / companion / ...) sets the next turn's endpointing

    async def respond(self, transcript: str, source: str = "voice") -> str:
        """Returns "spoken" or "skipped" (an outdated plain reply)."""
        idx = self.turns.reasoning_started(transcript, t=time.time(), source=source)
        await self._mark_thinking(True)
        # Never silence: `ask` turns any reasoning failure into a fixed spoken line.
        try:
            reply = await self.ask(transcript)
        finally:
            await self._mark_thinking(False)
        self.turns.reasoning_done(idx, time.time(), reply.text, reply.mode, reply.round_trip_ms)
        if self.on_mode is not None:
            try:
                self.on_mode(reply.mode)
            except Exception:  # noqa: BLE001 - a timing tweak must never break a turn
                logger.debug("could not apply the endpointing mode", exc_info=True)
        if not should_speak(reply, self.turns.is_stale(idx)):
            # Reasoning ran (so its state stays consistent) but the user has spoken again: stay quiet
            # and leave the screen alone; the newest sentence will be answered instead.
            logger.info("dropping outdated reply for turn %s (a newer sentence arrived)", idx)
            self.turns.skip(idx, "stale")
            return "skipped"
        try:
            await self.publish(reply, idx)  # the screen first, so it changes as Arjun starts to speak
        except Exception:  # noqa: BLE001 - a screen update must never silence the reply
            logger.exception("could not publish the screen attributes for turn %s", idx)
        self.turns.speaking_for(idx)
        try:
            await self.say(self.speakable(reply))
        except Exception:  # noqa: BLE001 - TTS failure must be logged, not crash the session
            logger.exception("TTS failed for reply (mode=%s)", reply.mode)
            if reply.mode != "fallback":
                try:
                    await self.say(self.fallback_text())
                except Exception:  # noqa: BLE001
                    logger.exception("TTS fallback also failed")
        return "spoken"

    async def _mark_thinking(self, on: bool) -> None:
        if self.thinking is None:
            return
        try:
            await self.thinking(on)
        except Exception:  # noqa: BLE001 - a marker must never break a turn
            logger.debug("could not publish the thinking marker", exc_info=True)
