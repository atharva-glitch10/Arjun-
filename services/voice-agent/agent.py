"""LiveKit Agents worker: Gnani Prisma (STT) + Gnani Timbre (TTS), reasoning over HTTP.

STATUS: TTS verified live through the plugin (2026-10-21). A full spoken turn has NOT yet run
end to end (T4). No LLM is configured: every reply is the templated text returned by reasoning
/turn. Dispatch is EXPLICIT: the worker registers as AGENT_NAME ("arjun") and only joins rooms whose
token/room config dispatches that name (see scripts/make_token.py). The tested logic is in bridge.py.
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

import applog
from bridge import fallback_text, reply_or_fallback, should_speak
from dotenv import dotenv_values
from livekit import agents
from livekit.agents import Agent, AgentSession, StopResponse
from livekit.plugins import gnani, silero
from turnlog import TurnLog

logger = logging.getLogger("arjun.agent")

REQUIRED_ENV = ("GNANI_API_KEY", "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
# ARJUN_* are non-secret settings (agent name, user id, endpointing). REASONING_URL is NOT loaded
# from .env on purpose: dev-up.ps1 sets the local value and .env may hold the compose hostname.
ENV_PREFIXES = ("GNANI_", "LIVEKIT_", "ARJUN_")


def load_agent_env(env_file: Path | None = None) -> None:
    """Copy only GNANI_* / LIVEKIT_* / ARJUN_* from the root .env into os.environ; .env wins over inherited values.

    .env must win: a shell started before a key rotation still carries the old keys, and using those
    gives 403 API_KEY_INACTIVE (seen 2026-10-21). Variables absent from .env keep their environment value.

    Exits with the NAMES of missing required variables; values are never printed.
    """
    path = env_file or Path(__file__).resolve().parents[2] / ".env"
    values = dotenv_values(path) if path.is_file() else {}
    for name, value in values.items():
        if name.startswith(ENV_PREFIXES) and value:
            os.environ[name] = value
    missing = [n for n in REQUIRED_ENV if not os.environ.get(n)]
    if missing:
        sys.exit(f"voice-agent: missing required environment variables: {', '.join(missing)} (set them in {path})")


load_agent_env()  # job subprocesses re-import this module; they inherit the already-set env
applog.setup_file_log()  # logs/voice-agent.app.log, written from inside this process (see applog.py)

USER_ID = int(os.environ.get("ARJUN_USER_ID", "1"))  # demo: one synthetic user per deployment
# "mr-IN", or "en-IN,hi-IN" for the plugin's code-mixed mode. Marathi *streaming* support is still
# unconfirmed (CLAUDE.md open question 1); set GNANI_USE_STREAMING=0 to fall back to non-streaming.
STT_LANGUAGE = os.environ.get("GNANI_STT_LANGUAGE", "mr-IN")
USE_STREAMING = os.environ.get("GNANI_USE_STREAMING", "1") == "1"
# Gnani TTS now accepts only timbre-v2.5 / timbre-v3.0 and requires a voice (checked 2026-10-21 against the
# REST API); the plugin's own default model (timbre-v2.0) and voice (Pranav) are out of date. `language` is
# only sent by the plugin for timbre-v2.5.
TTS_MODEL = os.environ.get("GNANI_TTS_MODEL", "timbre-v2.5")
TTS_VOICE = os.environ.get("GNANI_TTS_VOICE", "Omkar")
TTS_LANGUAGE = os.environ.get("GNANI_TTS_LANGUAGE", "mr-IN")
# Explicit dispatch name. An unnamed worker was never sent into Console/Playground rooms (2026-10-21).
AGENT_NAME = os.environ.get("ARJUN_AGENT_NAME", "arjun")
# Seconds of silence before end of turn. PLACEHOLDERS: elderly speakers pause mid-sentence, so start
# longer than the library default and tune on real recordings (CLAUDE.md: measure, don't guess).
MIN_ENDPOINTING_S = float(os.environ.get("ARJUN_MIN_ENDPOINTING_S", "1.0"))
MAX_ENDPOINTING_S = float(os.environ.get("ARJUN_MAX_ENDPOINTING_S", "3.0"))


class Arjun(Agent):
    def __init__(self, turns: TurnLog) -> None:
        self.turns = turns
        # No LLM on the session; instructions are unused but required by the base class.
        super().__init__(instructions="Arjun is an AI voice companion. Replies come from reasoning.")

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:  # type: ignore[no-untyped-def]
        """Send the transcript to reasoning and speak its templated reply (no built-in LLM)."""
        transcript = new_message.text_content or ""
        if not transcript.strip():
            raise StopResponse()
        idx = self.turns.reasoning_started(transcript)
        # Never silence: reply_or_fallback turns any reasoning failure into a fixed spoken line.
        reply = await asyncio.to_thread(reply_or_fallback, USER_ID, transcript, STT_LANGUAGE)
        self.turns.reasoning_done(idx, time.time(), reply.text, reply.mode)
        if not should_speak(reply, self.turns.is_stale(idx)):
            # Reasoning ran (so its state stays consistent) but the user has spoken again: stay quiet
            # and let the newest sentence be answered instead of replying to an old one.
            logger.info("dropping outdated reply for turn %s (a newer sentence arrived)", idx)
            self.turns.skip(idx, "stale")
            raise StopResponse()
        self.turns.speaking_for(idx)
        try:
            await self.session.say(reply.text)
        except Exception:  # noqa: BLE001 - TTS failure must be logged, not crash the session
            logger.exception("TTS failed for reply (mode=%s)", reply.mode)
            if reply.mode != "fallback":
                try:
                    await self.session.say(fallback_text(STT_LANGUAGE))
                except Exception:  # noqa: BLE001
                    logger.exception("TTS fallback also failed")
        raise StopResponse()  # suppress the default LLM reply


async def entrypoint(ctx: agents.JobContext) -> None:
    applog.setup_file_log()  # the CLI may have reset logging after import; make sure the file handler is on
    await ctx.connect()
    session = AgentSession(
        stt=gnani.STT(language=STT_LANGUAGE, use_streaming=USE_STREAMING),  # Prisma
        tts=gnani.TTS(model=TTS_MODEL, voice=TTS_VOICE, language=TTS_LANGUAGE),  # Timbre; key from GNANI_API_KEY
        vad=silero.VAD.load(),
        min_endpointing_delay=MIN_ENDPOINTING_S,
        max_endpointing_delay=MAX_ENDPOINTING_S,
    )
    turns = TurnLog(language_selected=STT_LANGUAGE)

    @session.on("user_state_changed")
    def _on_user_state(ev) -> None:  # type: ignore[no-untyped-def]
        if ev.old_state == "speaking" and ev.new_state == "listening":
            turns.end_of_speech(ev.created_at)

    @session.on("user_input_transcribed")
    def _on_transcript(ev) -> None:  # type: ignore[no-untyped-def]
        if ev.is_final and ev.transcript.strip():
            turns.final_transcript(ev.created_at, ev.transcript, str(ev.language) if ev.language else None)

    @session.on("agent_state_changed")
    def _on_agent_state(ev) -> None:  # type: ignore[no-untyped-def]
        if ev.new_state == "speaking":
            turns.agent_speaking(ev.created_at)

    @session.on("error")
    def _on_error(ev) -> None:  # type: ignore[no-untyped-def]
        # STT / TTS / plugin failures: type and a short message only (never headers or keys).
        err = getattr(ev, "error", ev)
        logger.error("session error: %s: %s", type(err).__name__, str(err)[:300])

    @session.on("close")
    def _on_close(ev) -> None:  # type: ignore[no-untyped-def]
        turns.close()

    await session.start(room=ctx.room, agent=Arjun(turns))


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, agent_name=AGENT_NAME))
