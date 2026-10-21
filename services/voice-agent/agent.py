"""LiveKit Agents worker: Gnani Prisma (STT) + Gnani Timbre (TTS), reasoning over HTTP.

STATUS: names and constructor arguments checked against livekit-plugins-gnani 1.8.6 / livekit-agents
1.8.6 (imports and signatures only). NOT yet run against the live Gnani or LiveKit services - that
needs GNANI_API_KEY and LIVEKIT_* in the root .env. No LLM is configured: every reply is the templated text
returned by reasoning /turn. The tested logic is in bridge.py.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

from bridge import ask_reasoning
from dotenv import dotenv_values
from livekit import agents
from livekit.agents import Agent, AgentSession, StopResponse
from livekit.plugins import gnani, silero
from turnlog import TurnLog

REQUIRED_ENV = ("GNANI_API_KEY", "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
ENV_PREFIXES = ("GNANI_", "LIVEKIT_")


def load_agent_env(env_file: Path | None = None) -> None:
    """Copy only GNANI_* / LIVEKIT_* from the root .env into os.environ; .env wins over inherited values.

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
        reply = await asyncio.to_thread(ask_reasoning, USER_ID, transcript)
        self.turns.reasoning_done(time.time(), reply.text, reply.mode)
        await self.session.say(reply.text)
        raise StopResponse()  # suppress the default LLM reply


async def entrypoint(ctx: agents.JobContext) -> None:
    await ctx.connect()
    session = AgentSession(
        stt=gnani.STT(language=STT_LANGUAGE, use_streaming=USE_STREAMING),  # Prisma
        tts=gnani.TTS(model=TTS_MODEL, voice=TTS_VOICE, language=TTS_LANGUAGE),  # Timbre; key from GNANI_API_KEY
        vad=silero.VAD.load(),
        min_endpointing_delay=0.7,  # placeholder, see bridge.endpointing_delay
        max_endpointing_delay=3.0,
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

    await session.start(room=ctx.room, agent=Arjun(turns))


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
