"""LiveKit Agents worker: Gnani Prisma (STT) + Gnani Timbre (TTS), reasoning over HTTP.

STATUS: names and constructor arguments checked against livekit-plugins-gnani 1.8.6 / livekit-agents
1.8.6 (imports and signatures only). NOT yet run against the live Gnani or LiveKit services - that
needs GNANI_API_KEY and LIVEKIT_* in .env. No LLM is configured: every reply is the templated text
returned by reasoning /turn. The tested logic is in bridge.py.
"""

import asyncio
import os

from bridge import ask_reasoning
from livekit import agents
from livekit.agents import Agent, AgentSession, StopResponse
from livekit.plugins import gnani, silero

USER_ID = int(os.environ.get("ARJUN_USER_ID", "1"))  # demo: one synthetic user per deployment
# "mr-IN", or "en-IN,hi-IN" for the plugin's code-mixed mode. Marathi *streaming* support is still
# unconfirmed (CLAUDE.md open question 1); set GNANI_USE_STREAMING=0 to fall back to non-streaming.
STT_LANGUAGE = os.environ.get("GNANI_STT_LANGUAGE", "mr-IN")
USE_STREAMING = os.environ.get("GNANI_USE_STREAMING", "1") == "1"
TTS_VOICE = os.environ.get("GNANI_TTS_VOICE", "Pranav")  # plugin voices: Pranav, Kaveri, Shubhra, Deepak
TTS_LANGUAGE = os.environ.get("GNANI_TTS_LANGUAGE", "mr-IN")


class Arjun(Agent):
    def __init__(self) -> None:
        # No LLM on the session; instructions are unused but required by the base class.
        super().__init__(instructions="Arjun is an AI voice companion. Replies come from reasoning.")

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:  # type: ignore[no-untyped-def]
        """Send the transcript to reasoning and speak its templated reply (no built-in LLM)."""
        transcript = new_message.text_content or ""
        if not transcript.strip():
            raise StopResponse()
        reply = await asyncio.to_thread(ask_reasoning, USER_ID, transcript)
        await self.session.say(reply.text)
        raise StopResponse()  # suppress the default LLM reply


async def entrypoint(ctx: agents.JobContext) -> None:
    await ctx.connect()
    session = AgentSession(
        stt=gnani.STT(language=STT_LANGUAGE, use_streaming=USE_STREAMING),  # Prisma
        tts=gnani.TTS(voice=TTS_VOICE, language=TTS_LANGUAGE),  # Timbre; key from GNANI_API_KEY
        vad=silero.VAD.load(),
        min_endpointing_delay=0.7,  # placeholder, see bridge.endpointing_delay
        max_endpointing_delay=3.0,
    )
    await session.start(room=ctx.room, agent=Arjun())


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
