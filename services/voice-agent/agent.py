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
from audiowarm import warm_audio_resampler
from bridge import (
    claim_next_delivery,
    closing_text,
    fallback_text,
    mark_delivery_spoken,
    release_delivery,
    reply_or_fallback,
    session_busy,
)
from delivery import DeliveryLoop
from dotenv import dotenv_values
from endpointing import ConjunctionHold, EndpointingPolicy, turn_detection_from_env
from idle import IdleCloser, IdlePolicy
from livekit import agents
from livekit.agents import (
    DEFAULT_API_CONNECT_OPTIONS,
    Agent,
    AgentSession,
    APIStatusError,
    StopResponse,
    room_io,
)
from livekit.agents import tts as lk_tts
from livekit.plugins import gnani, silero
from livekit.plugins.gnani.tts import SSEChunkedStream
from media import ATTR_MEDIA, MediaState, should_send, strip_wake_word
from responder import Responder
from screenstate import publish_closed, publish_delivery, publish_screen, publish_thinking
from sessionstate import SessionState
from ttsgate import TtsGate
from turnlog import TurnLog
from usermeta import user_id_from_metadata
from voice import stt_options, tts_choice, tts_text

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
# Gnani TTS accepts timbre-v2.5 / timbre-v3.0 and requires a voice (checked 2026-10-21 against the REST API).
# Default now: timbre-v3.0 (voice tags) over SSE. v3.0 + "Avinash" is UNVERIFIED on our key: the first synthesis
# of each worker process is a probe, and on failure the session uses the verified v2.5 + "Omkar" instead.
TTS = tts_choice()
TTS_MODEL, TTS_VOICE, TTS_LANGUAGE = TTS["model"], TTS["voice"], TTS["language"]
STT_OPTIONS = stt_options()  # format="transcribe" (ITN) + itn_native_numerals, per the project brief
# Explicit dispatch name. An unnamed worker was never sent into Console/Playground rooms (2026-10-21).
AGENT_NAME = os.environ.get("ARJUN_AGENT_NAME", "arjun")
# Seconds of silence before end of turn: mode-aware since task D (2026-10-31), see endpointing.py. Care 0.8 / 2.5 s,
# companion / story 1.6 / 4.0 s, chosen by the mode of the LAST reply. PLACEHOLDERS until tuned on real elderly speech.


TTS_GATE = TtsGate()  # Timbre allows ONE active request at a time (429 RATE_LIMITED otherwise); see ttsgate.py


def _timbre_busy(exc: Exception) -> bool:
    return isinstance(exc, APIStatusError) and exc.status_code == 429


class _GatedSse(SSEChunkedStream):
    """One SSE request at a time per process, a busy answer retried a couple of times (ttsgate.py)."""

    async def _run(self, output_emitter) -> None:  # type: ignore[no-untyped-def]
        await TTS_GATE.run(lambda: SSEChunkedStream._run(self, output_emitter), _timbre_busy)


class SseTimbre(gnani.TTS):
    """Timbre over Server-Sent Events. Marked non-streaming on purpose: LiveKit then sends each SENTENCE to
    synthesize() (SSE on the plugin's pooled HTTP session) as soon as it is ready, instead of opening a new
    WebSocket for every reply (~1 s connect, measured 2026-10-26)."""

    def __init__(self, **kw) -> None:  # type: ignore[no-untyped-def]
        super().__init__(synthesize_method="sse", **kw)
        self._capabilities = lk_tts.TTSCapabilities(streaming=False)

    def synthesize(self, text, *, conn_options=DEFAULT_API_CONNECT_OPTIONS):  # type: ignore[no-untyped-def]
        return _GatedSse(tts=self, input_text=text, conn_options=conn_options)


def make_tts(model: str, voice: str):  # type: ignore[no-untyped-def]
    kw = {"model": model, "voice": voice, "language": TTS_LANGUAGE}
    if TTS["method"] == "sse":
        return SseTimbre(**kw)
    return gnani.TTS(synthesize_method=TTS["method"], **kw)  # "websocket" / "rest", the old path


_PROBED: dict[str, bool] = {}  # model -> works, per worker process


async def working_tts():  # type: ignore[no-untyped-def]
    """(tts, model) for this session: the configured Timbre if a one-word probe works, else the verified one."""
    primary = make_tts(TTS_MODEL, TTS_VOICE)
    if TTS_MODEL == TTS["fallback_model"] and TTS_VOICE == TTS["fallback_voice"]:
        return primary, TTS_MODEL
    if _PROBED.get(TTS_MODEL) is None:
        try:
            await asyncio.wait_for(primary.synthesize("नमस्कार").collect(), timeout=8)
            _PROBED[TTS_MODEL] = True
        except Exception as exc:  # noqa: BLE001 - any failure means: use the voice we know works
            logger.error("TTS %s / %s failed its probe (%s); using %s / %s", TTS_MODEL, TTS_VOICE,
                         type(exc).__name__, TTS["fallback_model"], TTS["fallback_voice"])
            _PROBED[TTS_MODEL] = False
    if _PROBED[TTS_MODEL]:
        return primary, TTS_MODEL
    return make_tts(TTS["fallback_model"], TTS["fallback_voice"]), TTS["fallback_model"]


class Arjun(Agent):
    def __init__(
        self, turns: TurnLog, responder: Responder, state: SessionState, policy: IdlePolicy, hold: ConjunctionHold,
        media: MediaState,
    ) -> None:
        self.turns = turns
        self.media = media
        self.hold = hold
        self.responder = responder
        self.state = state
        self.policy = policy
        # No LLM on the session; instructions are unused but required by the base class.
        super().__init__(instructions="Arjun is an AI voice companion. Replies come from reasoning.")

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:  # type: ignore[no-untyped-def]
        """Send the transcript to reasoning and speak its templated reply (no built-in LLM)."""
        transcript = new_message.text_content or ""
        # While a video plays, most of what the mic hears is the video. Send only her own words, a bare
        # control, or a safety phrase; the check is local, so safety never waits for another service.
        if not should_send(transcript, self.media.playing):
            logger.info("ignored_media (%d characters; the words are not kept)", len(transcript))
            self.turns.ignore_collected("ignored_media")
            raise StopResponse()
        if self.media.playing:  # "अर्जुन, थांबव" -> reasoning gets "थांबव"
            transcript = strip_wake_word(transcript)
        self.policy.touch()
        # A sentence that ends in "आणि / पण / म्हणजे / की" is not finished: wait for the rest (endpointing.py).
        text = await self.hold.settle(transcript)
        if text is None or not text.strip():  # held for more speech, or nothing to answer
            raise StopResponse()
        async with self.state.turn():  # while a spoken turn is being answered the session is not idle / quiet
            await self.responder.respond(text, "voice")
        self.policy.touch()
        raise StopResponse()  # suppress the default LLM reply


def prewarm(proc: agents.JobProcess) -> None:
    """Once per job process, before any session: warm the resampler and load the VAD model."""
    warm_audio_resampler()
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: agents.JobContext) -> None:
    warm_audio_resampler()  # idempotent, a safety net
    applog.setup_file_log() # the CLI may have reset logging after import; make sure the file handler is on
    await ctx.connect()
    timbre, active_model = await working_tts()  # Timbre v3.0 over SSE, or the verified fallback
    logger.info("TTS %s via %s; STT %s", active_model, TTS["method"], STT_OPTIONS)
    endpointing = EndpointingPolicy()  # starts in care timing; each reply's mode sets the next turn's
    handling: dict = {"endpointing": endpointing.options()}  # type: ignore[type-arg]
    detection = turn_detection_from_env()  # "vad" by default; None = LiveKit's cloud detector (see endpointing.py)
    if detection is not None:
        handling["turn_detection"] = detection
    logger.info("turn detection %s, endpointing %s", detection or "auto (cloud)", endpointing.options())
    session = AgentSession(
        stt=gnani.STT(language=STT_LANGUAGE, use_streaming=USE_STREAMING, **STT_OPTIONS),  # Prisma
        tts=timbre,  # key from GNANI_API_KEY
        vad=ctx.proc.userdata.get("vad") or silero.VAD.load(),
        turn_handling=handling,
    )
    user_started = asyncio.Event()  # set whenever she starts speaking (the conjunction hold waits on it)

    async def wait_for_speech(timeout: float) -> bool:
        user_started.clear()
        if state.user == "speaking":  # `state` is created below, before any turn can complete
            return True
        try:
            await asyncio.wait_for(user_started.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    hold = ConjunctionHold(endpointing, wait_for_speech)

    def apply_mode(mode: str) -> None:
        endpointing.set_mode(mode)
        session.update_options(endpointing_opts=endpointing.options())  # type: ignore[arg-type]
    # One JSON line per turn, tagged with this LiveKit job id. The numbers start from the wall clock, so a browser that
    # drops and rejoins (a new job, a new TurnLog) continues ABOVE the old session instead of restarting at 1.
    turns = TurnLog(language_selected=STT_LANGUAGE, session=ctx.job.id, start=TurnLog.base_for(time.time()))

    # The elder's user id travels in the dispatch metadata from /livekit/token; ARJUN_USER_ID is the fallback.
    from_metadata = user_id_from_metadata(ctx.job.metadata, 0)
    user_id = from_metadata or USER_ID
    logger.info("session serves user %s (%s)", user_id, "dispatch metadata" if from_metadata else "ARJUN_USER_ID fallback")

    async def ask(text: str):  # type: ignore[no-untyped-def]
        return await asyncio.to_thread(reply_or_fallback, user_id, text, STT_LANGUAGE)

    state = SessionState()
    policy = IdlePolicy()
    speech_lock = asyncio.Lock()  # one line at a time: a reply, a reminder and the closing line never overlap
    session_id = ctx.job.id

    async def say_locked(text: str) -> None:
        async with speech_lock:
            await session.say(text)

    async def speak_checked(text: str) -> bool:
        """Speak and say whether it REALLY played to the end. False = the elder interrupted. Raises if no audio was
        produced (awaiting a speech handle never raises by itself, so a TTS failure would otherwise look like success)."""
        async with speech_lock:
            before = state.speaking_count
            handle = session.say(text)
            await handle
            if handle.interrupted:
                return False
            if handle.exception() is not None or state.speaking_count == before:
                raise RuntimeError("the speech did not play")
            return True

    media = MediaState()  # media mode: while a video plays, only "अर्जुन ..." / stop / safety phrases get through

    async def publish(reply, turn) -> None:  # type: ignore[no-untyped-def]
        await publish_screen(ctx.room.local_participant, reply, turn)  # screen + "arjun.action" for the page
        media.on_action(reply.action)

    @ctx.room.on("participant_attributes_changed")
    def _on_page_attributes(changed, participant) -> None:  # type: ignore[no-untyped-def]
        if ATTR_MEDIA in changed:  # the elder page says whether its player is playing
            media.on_page_state(changed[ATTR_MEDIA])

    @ctx.room.on("participant_disconnected")
    def _on_page_left(participant) -> None:  # type: ignore[no-untyped-def]
        media.reset()

    responder = Responder(
        turns,
        ask,
        say_locked,
        publish,
        lambda: fallback_text(STT_LANGUAGE),
        thinking=lambda on: publish_thinking(ctx.room.local_participant, on),  # "विचार करतोय…"
        speakable=lambda reply: tts_text(reply.text, reply.speech, active_model),  # tags only for Timbre v3
        on_mode=apply_mode,
    )

    async def on_tapped_text(sess, ev) -> None:  # type: ignore[no-untyped-def]
        """A button tap on the elder screen arrives as text on "lk.chat": same path as a spoken turn.
        LiveKit's default would call an LLM we do not have."""
        policy.touch()
        await sess.interrupt()  # a tap while Arjun is talking cuts the old line off
        async with state.turn():
            await responder.respond(ev.text, "tap")
        policy.touch()

    @session.on("user_state_changed")
    def _on_user_state(ev) -> None:  # type: ignore[no-untyped-def]
        state.on_user_state(ev.new_state)
        if ev.new_state == "speaking":
            user_started.set()
        policy.touch()
        if ev.old_state == "speaking" and ev.new_state == "listening":
            turns.end_of_speech(ev.created_at)

    @session.on("user_input_transcribed")
    def _on_transcript(ev) -> None:  # type: ignore[no-untyped-def]
        if ev.is_final and ev.transcript.strip():
            turns.final_transcript(ev.created_at, ev.transcript, str(ev.language) if ev.language else None)

    @session.on("agent_state_changed")
    def _on_agent_state(ev) -> None:  # type: ignore[no-untyped-def]
        state.on_agent_state(ev.new_state)
        policy.touch()  # the 60 s idle clock starts when Arjun stops talking
        if ev.new_state == "speaking":
            turns.agent_speaking(ev.created_at)

    @session.on("error")
    def _on_error(ev) -> None:  # type: ignore[no-untyped-def]
        # STT / TTS / plugin failures: type and a short message only (never headers or keys).
        err = getattr(ev, "error", ev)
        logger.error("session error: %s: %s", type(err).__name__, str(err)[:300])

    background: list[asyncio.Task[None]] = []

    @session.on("close")
    def _on_close(ev) -> None:  # type: ignore[no-untyped-def]
        turns.close()
        for task in background:
            task.cancel()

    await session.start(
        room=ctx.room,
        agent=Arjun(turns, responder, state, policy, hold, media),
        room_options=room_io.RoomOptions(text_input=room_io.TextInputOptions(text_input_cb=on_tapped_text)),
    )

    # ---- T8: queued reminders / medicines are spoken here; an idle session closes itself -------------------
    async def claim_next():  # type: ignore[no-untyped-def]
        return await asyncio.to_thread(claim_next_delivery, user_id, session_id)

    async def mark_spoken(delivery_id: int) -> None:
        await asyncio.to_thread(mark_delivery_spoken, user_id, delivery_id, session_id)

    async def release(delivery_id: int, reason: str) -> None:
        await asyncio.to_thread(release_delivery, user_id, delivery_id, session_id, reason)

    async def publish_item(item: dict) -> None:  # type: ignore[type-arg]
        policy.touch()
        await publish_delivery(ctx.room.local_participant, item, turns.bump())

    async def get_busy():  # type: ignore[no-untyped-def]
        return await asyncio.to_thread(session_busy, user_id)

    async def say_closing() -> str:
        try:
            return "done" if await speak_checked(closing_text(STT_LANGUAGE)) else "interrupted"
        except Exception:  # noqa: BLE001 - even if the line cannot be spoken, an idle session still ends
            logger.exception("could not speak the closing line")
            return "done"

    async def announce_closed() -> None:
        await publish_closed(ctx.room.local_participant, turns.bump())

    async def leave() -> None:
        await asyncio.sleep(0.3)  # let the "closed" attribute reach the app before the agent leaves
        ctx.shutdown(reason=f"idle for {policy.idle_after_s:.0f} s")

    deliveries = DeliveryLoop(
        claim_next=claim_next, spoken=mark_spoken, release=release, speak=speak_checked, publish=publish_item,
        can_speak=lambda: state.quiet(speech_lock.locked()),
    )
    closer = IdleCloser(
        policy, quiet=lambda: state.quiet(speech_lock.locked()), get_busy=get_busy, say_closing=say_closing,
        publish_closed=announce_closed, shutdown=leave,
    )
    background += [asyncio.create_task(deliveries.run()), asyncio.create_task(closer.run())]


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm, agent_name=AGENT_NAME))
