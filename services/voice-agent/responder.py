"""The ONE place a user turn becomes a spoken reply, whether it was spoken or tapped.

A tapped "हो" / "नको" is sent to the agent as text and goes through exactly the same steps as a spoken
one: reasoning (which checks the pending action), the stale / safety / confirmation rules in
`bridge.should_speak`, the screen attributes, then speech. There is no second path to keep in step.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from bridge import BridgeReply, should_speak
from turnlog import TurnLog

logger = logging.getLogger("arjun.responder")

PREPARE_WAIT_S = 0.35  # /turn/prepare is asked for within 0.3 s; this is the hard stop
HOLD_LINE = "थोडा वेळ लागतोय…"  # used when prepare gave no translated hold line
SLOW_AFTER_S = 4.0  # hold line if the answer is still not here after this long (4 s since 2026-11-09; the web turn budget is 6 s)


class Responder:
    def __init__(
        self,
        turns: TurnLog,
        ask: Callable[[str], Awaitable[BridgeReply]],
        say: Callable[[str], Awaitable[bool | None]],
        publish: Callable[[BridgeReply, int], Awaitable[None]],
        thinking: Callable[[bool], Awaitable[None]] | None = None,
        speakable: Callable[[BridgeReply], str] | None = None,
        say_reply: Callable[[BridgeReply], Awaitable[bool | None]] | None = None,
        on_mode: Callable[[str], None] | None = None,
        prepare: Callable[[str], Awaitable[dict | None]] | None = None,  # type: ignore[type-arg]
        slow_after_s: float = SLOW_AFTER_S,
    ) -> None:
        self.prepare, self.slow_after_s = prepare, slow_after_s
        self.turns, self.ask, self.say, self.publish = turns, ask, say, publish
        self.thinking = thinking  # the "विचार करतोय…" marker on the elder screen
        # reply -> the exact text for TTS (tagged for Timbre v3, plain otherwise); default: the screen text
        self.speakable = speakable or (lambda r: r.text)
        self.say_reply = say_reply
        self.on_mode = on_mode  # the mode of each reply (care / companion / ...) sets the next turn's endpointing

    async def respond(self, transcript: str, source: str = "voice") -> str:
        """Returns "spoken" or "skipped" (an outdated plain reply)."""
        idx = self.turns.reasoning_started(transcript, t=time.time(), source=source)
        await self._mark_thinking(True)
        # Never silence: `ask` turns any reasoning failure into a fixed spoken line.
        try:
            reply = await self._ask_with_filler(transcript)
        finally:
            await self._mark_thinking(False)
        self.turns.reasoning_done(
            idx, time.time(), reply.text, reply.mode, reply.round_trip_ms, intent=reply.intent, source=reply.source,
            action_type=(reply.action or {}).get("type", ""),
        )
        if reply.silent:
            self.turns.not_spoken(idx, "no_reply")
            return "silent"
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
            played = await self.say_reply(reply) if self.say_reply else await self.say(self.speakable(reply))
            if played is False:  # cut off before any audio (she spoke again): the log says so instead of going silent
                self.turns.not_spoken(idx, "interrupted")
            else:
                self.turns.speech_finished(idx)
        except Exception:  # noqa: BLE001 - TTS failure must be logged, not crash the session
            logger.exception("TTS failed for reply (mode=%s)", reply.mode)
            self.turns.not_spoken(idx, "tts_failed")
        return "spoken"

    async def _ask_with_filler(self, transcript: str) -> BridgeReply:
        """/turn runs the whole time. In parallel: /turn/prepare (<=0.3 s); if it says a web lookup is coming, the
        filler is spoken at once; if the answer is still not here after `slow_after_s`, one "it takes a while" line.
        A failed or slow prepare just means no filler. The answer itself always comes from `ask` (the /turn call)."""
        t0 = time.monotonic()
        answer = asyncio.ensure_future(self.ask(transcript))
        prep = None
        if self.prepare is not None:
            try:
                prep = await asyncio.wait_for(self.prepare(transcript), timeout=PREPARE_WAIT_S)
            except Exception:  # noqa: BLE001 - timeout or any error: no filler, the turn goes on
                prep = None
        web = bool(prep and prep.get("needs_web"))
        if web and prep and prep.get("filler") and not answer.done():
            await self._say_quiet(str(prep["filler"]))
        wait = self.slow_after_s - (time.monotonic() - t0)
        if wait > 0:
            await asyncio.wait({answer}, timeout=wait)
        if not answer.done():  # any slow turn, web or not
            await self._say_quiet(str((prep or {}).get("hold") or HOLD_LINE))
        return await answer

    async def _say_quiet(self, text: str) -> None:
        try:
            await self.say(text)
        except Exception:  # noqa: BLE001 - a filler must never break the turn
            logger.debug("could not speak the filler", exc_info=True)

    async def _mark_thinking(self, on: bool) -> None:
        if self.thinking is None:
            return
        try:
            await self.thinking(on)
        except Exception:  # noqa: BLE001 - a marker must never break a turn
            logger.debug("could not publish the thinking marker", exc_info=True)
