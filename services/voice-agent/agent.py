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
import voiceprovider
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
from bridge import media_stopped as notify_media_stopped
from bridge import video_call_stopped as notify_video_call_stopped
from delivery import DeliveryLoop
from dotenv import dotenv_values
from endpointing import ConjunctionHold, EndpointingPolicy, turn_detection_from_env
from familyroom import FamilyPresence
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

try:  # TESTING switch (voiceprovider.py). Imported here: a plugin must be registered on the main thread.
    from livekit.plugins import sarvam
except ImportError:  # the Gnani path does not need it
    sarvam = None
from livekit.plugins.gnani.tts import SSEChunkedStream
from media import (
    ATTR_MEDIA,
    ATTR_VIDEO_CALL,
    MediaState,
    is_bare_control,
    is_system_marker,
    should_send,
    strip_wake_word,
)
from responder import Responder
from safety_words import is_safety_phrase
from screenstate import publish_closed, publish_delivery, publish_screen, publish_thinking
from sessionstate import SessionState
from ttsgate import TtsGate
from turnlog import TurnLog
from usermeta import user_id_from_metadata
from voice import slower_text, stt_options, tts_choice, tts_text

logger = logging.getLogger("arjun.agent")

REQUIRED_ENV = ("GNANI_API_KEY", "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
# TESTING switch (voiceprovider.py): with ARJUN_VOICE_PROVIDER=sarvam the Gnani key is not needed, SARVAM_API_KEY is.
SARVAM_REQUIRED_ENV = ("SARVAM_API_KEY", "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
# ARJUN_* are non-secret settings (agent name, user id, endpointing). REASONING_URL is NOT loaded
# from .env on purpose: dev-up.ps1 sets the local value and .env may hold the compose hostname.
ENV_PREFIXES = ("GNANI_", "LIVEKIT_", "ARJUN_")


def load_agent_env(env_file: Path | None = None) -> None:
    """Copy voice settings plus CORE_API_KEY for the local briefing endpoint; .env wins over inherited values.

    .env must win: a shell started before a key rotation still carries the old keys, and using those
    gives 403 API_KEY_INACTIVE (seen 2026-10-21). Variables absent from .env keep their environment value.

    Exits with the NAMES of missing required variables; values are never printed.
    """
    path = env_file or Path(__file__).resolve().parents[2] / ".env"
    values = dotenv_values(path) if path.is_file() else {}
    for name, value in values.items():
        if (name.startswith(ENV_PREFIXES) or name in ("SARVAM_API_KEY", "CORE_API_KEY")) and value:
            os.environ[name] = value
    sarvam_on = os.environ.get("ARJUN_VOICE_PROVIDER", "").strip().lower() == "sarvam"
    missing = [n for n in (SARVAM_REQUIRED_ENV if sarvam_on else REQUIRED_ENV) if not os.environ.get(n)]
    if missing:
        sys.exit(f"voice-agent: missing required environment variables: {', '.join(missing)} (set them in {path})")


load_agent_env()  # job subprocesses re-import this module; they inherit the already-set env
applog.setup_file_log()  # logs/voice-agent.app.log, written from inside this process (see applog.py)

USER_ID = int(os.environ.get("ARJUN_USER_ID", "1"))  # demo: one synthetic user per deployment
# "mr-IN", or "en-IN,hi-IN" for the plugin's code-mixed mode. Marathi *streaming* support is still
# unconfirmed (CLAUDE.md open question 1); set GNANI_USE_STREAMING=0 to fall back to non-streaming.
STT_LANGUAGE = os.environ.get("GNANI_STT_LANGUAGE", "mr-IN").strip()
USE_STREAMING = os.environ.get("GNANI_USE_STREAMING", "1") == "1"
# Gnani TTS accepts timbre-v2.5 / timbre-v3.0 and requires a voice (checked 2026-10-21 against the REST API).
# Default now: timbre-v3.0 (voice tags) over SSE. v3.0 + "Avinash" is UNVERIFIED on our key: the first synthesis
# of each worker process is a probe, and on failure the session uses the verified v2.5 + "Omkar" instead.
TTS = tts_choice()
TTS_MODEL, TTS_VOICE, TTS_LANGUAGE = TTS["model"], TTS["voice"], TTS["language"]
STT_OPTIONS = stt_options()  # only constructor options exposed by the pinned 1.8.6 plugin
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
        media: MediaState, family: FamilyPresence, user_id: int, event_say, call_active,
    ) -> None:
        self.turns = turns
        self.media = media
        self.family = family
        self.user_id = user_id
        self.event_say = event_say
        self.hold = hold
        self.responder = responder
        self.state = state
        self.policy = policy
        self.call_active = call_active
        # No LLM on the session; instructions are unused but required by the base class.
        super().__init__(instructions="Arjun is an AI voice companion. Replies come from reasoning.")

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:  # type: ignore[no-untyped-def]
        """Send the transcript to reasoning and speak its templated reply (no built-in LLM)."""
        transcript = new_message.text_content or ""
        if transcript.strip() == "[video_call_stopped]":
            await asyncio.to_thread(notify_video_call_stopped, self.user_id)
            logger.info("video call transient state cleared")
            raise StopResponse()
        if is_system_marker(transcript):
            # UI lifecycle markers are control events, never spoken user input.
            logger.info("video call event received: %s", transcript.strip().split("]", 1)[0][1:])
            if transcript.strip().startswith("[video_call_missed]"):
                await asyncio.to_thread(notify_video_call_stopped, self.user_id)
                name = transcript.partition("]")[2].strip()[:80] or "घरच्यांनी"
                await self.event_say(f"{name}नी उचलला नाही, मी निरोप ठेवला आहे.")
            raise StopResponse()
        if self.call_active[0]:
            # Calls are private family time. Only local safety detection and a short
            # stop command are relevant; the page handles ending, no reply is spoken.
            if is_bare_control(transcript):
                raise StopResponse()
            if not is_safety_phrase(transcript):
                self.turns.ignore_collected("video_call_active")
                raise StopResponse()
        # A family member is in the room: the mic hears them too, so Arjun says nothing at all.
        if self.family.present() and self.family.should_process(transcript):
            # Safety is evaluated locally in reasoning and remains audible during a family call.
            pass
        elif self.family.present():
            logger.info("family_in_room: Arjun stays quiet")
            self.turns.ignore_collected("family_in_room")
            raise StopResponse()
        # While a video plays, most of what the mic hears is the video. Send only her own words, a bare
        # control, or a safety phrase; the check is local, so safety never waits for another service.
        if not should_send(transcript, self.media.playing):
            logger.info("ignored_media (%d characters; the words are not kept)", len(transcript))
            self.turns.ignore_collected("ignored_media")
            raise StopResponse()
        if self.media.playing and not self.family.present():  # "अर्जुन, थांबव" -> reasoning gets "थांबव"
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
    use_sarvam = voiceprovider.provider() == "sarvam"  # TESTING switch; the default is the Gnani path below
    if use_sarvam:
        stt_plugin, tts_plugin = voiceprovider.make_sarvam(sarvam)
        active_model = voiceprovider.TTS_MODEL  # not a Timbre tag model: <tags> are stripped
        logger.info(voiceprovider.start_line())  # no Timbre probe
    else:
        tts_plugin, active_model = await working_tts()  # Timbre v3.0 over SSE, or the verified fallback
        # The pinned plugin does not expose model selection; it chooses its own endpoint/model.
        stt_plugin = gnani.STT(use_streaming=USE_STREAMING, **STT_OPTIONS)
        logger.info("stt stream recreated: fresh Gnani STT instance for voice session")
        logger.info("voice provider: gnani (stt prisma, tts %s)", active_model)
        logger.info("TTS %s via %s; STT %s", active_model, TTS["method"], STT_OPTIONS)
    endpointing = EndpointingPolicy()  # starts in care timing; each reply's mode sets the next turn's
    handling: dict = {"endpointing": endpointing.options()}  # type: ignore[type-arg]
    detection = turn_detection_from_env()  # "vad" by default; None = LiveKit's cloud detector (see endpointing.py)
    if detection is not None:
        handling["turn_detection"] = detection
    logger.info("turn detection %s, endpointing %s", detection or "auto (cloud)", endpointing.options())
    session = AgentSession(
        stt=stt_plugin,  # Prisma (GNANI_API_KEY) or, with the testing switch, Saaras (SARVAM_API_KEY)
        tts=tts_plugin,  # Timbre or, with the testing switch, Bulbul
        vad=ctx.proc.userdata.get("vad") or silero.VAD.load(),
        turn_handling=handling,
    )
    call_active = [False]
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
    turns = TurnLog(
        language_selected=STT_LANGUAGE, session=ctx.job.id, start=TurnLog.base_for(time.time()),
        stt_provider="sarvam" if use_sarvam else "gnani", tts_provider="sarvam" if use_sarvam else "gnani",
    )

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

    media = MediaState()  # enabled only after the elder page confirms the YouTube player is playing
    family = FamilyPresence()  # while a family member is in the room, Arjun stays quiet

    async def publish(reply, turn) -> None:  # type: ignore[no-untyped-def]
        await publish_screen(ctx.room.local_participant, reply, turn)  # screen + "arjun.action" for the page
        if reply.action and reply.action.get("type") == "open" and str(reply.action.get("kind", "")).startswith("youtube"):
            media_stop_notified[0] = False
        if reply.action and reply.action.get("type") == "control" and reply.action.get("kind") == "stop":
            set_media("stopped", "voice stop")
        media.on_action(reply.action)

    _heartbeat_task: list[asyncio.Task[None] | None] = [None]
    media_stop_notified = [True]

    def set_media(value: str, reason: str) -> None:
        was_playing = media.playing
        media.on_page_state(value)
        if media.playing != was_playing:
            logger.info("media mode %s: %s", "on" if media.playing else "off", reason)
            asyncio.create_task(_set_media_duck(False))
        if media.playing:
            media_stop_notified[0] = False
        elif not media_stop_notified[0]:
            media_stop_notified[0] = True
            asyncio.create_task(asyncio.to_thread(notify_media_stopped, user_id))

    async def _heartbeat_clear() -> None:
        await asyncio.sleep(30)
        if media.heartbeat_expired():
            set_media("stopped", "heartbeat timeout")

    @ctx.room.on("participant_attributes_changed")
    def _on_page_attributes(changed, participant) -> None:  # type: ignore[no-untyped-def]
        if ATTR_VIDEO_CALL in changed:
            call_active[0] = changed.get(ATTR_VIDEO_CALL) in ("ringing", "answered")
        if ATTR_MEDIA in changed or "arjun.media.heartbeat" in changed:
            val = changed.get(ATTR_MEDIA, participant.attributes.get(ATTR_MEDIA, "stopped"))
            if _heartbeat_task[0] is not None:
                _heartbeat_task[0].cancel()
                _heartbeat_task[0] = None
            if val == "playing":
                set_media("playing", "page playing report")
                _heartbeat_task[0] = asyncio.create_task(_heartbeat_clear())
            else:
                set_media("stopped", "page stopped report")

    def clear_media_timer() -> None:
        if _heartbeat_task[0] is not None:
            _heartbeat_task[0].cancel()
            _heartbeat_task[0] = None

    @ctx.room.on("participant_connected")
    def _on_family_joined(participant) -> None:  # type: ignore[no-untyped-def]
        family.joined(participant.identity)
        logger.info("participant joined (%s)", "family" if family.present() else "not family")
        if participant.identity == "family":
            asyncio.create_task(asyncio.to_thread(notify_video_call_stopped, user_id))

    @ctx.room.on("participant_disconnected")
    def _on_page_left(participant) -> None:  # type: ignore[no-untyped-def]
        family.left(participant.identity)
        if participant.identity == "family":
            asyncio.create_task(asyncio.to_thread(notify_video_call_stopped, user_id))
        if participant.identity != "family":
            clear_media_timer()
            set_media("stopped", "participant left")

    for _p in ctx.room.remote_participants.values():  # a family member may already be waiting
        family.joined(_p.identity)
        if _p.identity == "family":
            asyncio.create_task(asyncio.to_thread(notify_video_call_stopped, user_id))

    def speakable_text(reply) -> str:  # type: ignore[no-untyped-def]
        spoken = tts_text(reply.text, reply.speech, active_model)
        return slower_text(spoken) if (reply.speech_style or {}).get("rate") == "slow" else spoken

    responder = Responder(
        turns,
        ask,
        say_locked,
        publish,
        lambda: fallback_text(STT_LANGUAGE),
        thinking=lambda on: publish_thinking(ctx.room.local_participant, on),  # "विचार करतोय…"
        speakable=lambda reply: voiceprovider.sarvam_text(speakable_text(reply)) if use_sarvam else speakable_text(reply),
        on_mode=apply_mode,
    )

    async def on_tapped_text(sess, ev) -> None:  # type: ignore[no-untyped-def]
        """A button tap on the elder screen arrives as text on "lk.chat": same path as a spoken turn.
        LiveKit's default would call an LLM we do not have."""
        if is_system_marker(ev.text):
            marker = ev.text.strip()
            logger.info("video call event received: %s", marker.split("]", 1)[0][1:])
            if marker == "[video_call_stopped]" or marker.startswith("[video_call_missed]"):
                await asyncio.to_thread(notify_video_call_stopped, user_id)
            if marker.startswith("[video_call_missed]"):
                name = marker.partition("]")[2].strip()[:80] or "घरच्यांनी"
                await say_locked(f"{name}नी उचलला नाही, मी निरोप ठेवला आहे.")
            return
        if family.present():  # a family call is in progress: no third voice, even from a tap
            logger.info("family_in_room: tap ignored")
            return
        policy.touch()
        await sess.interrupt()  # a tap while Arjun is talking cuts the old line off
        async with state.turn():
            await responder.respond(ev.text, "tap")
        policy.touch()

    _media_utterance_task: list[asyncio.Task[None] | None] = [None]

    async def _set_media_duck(duck: bool) -> None:
        try:
            await ctx.room.local_participant.set_attributes({"arjun.media.duck": "1" if duck and media.playing else "0"})
        except Exception as exc:  # noqa: BLE001
            logger.info("media audio duck update failed (%s)", type(exc).__name__)

    async def _force_media_utterance_end() -> None:
        await asyncio.sleep(8)
        if media.playing and state.user == "speaking":
            logger.info("media utterance force-ended at 8 s")
            try:
                await session.commit_user_turn(transcript_timeout=2, stt_flush_duration=1)
            except Exception as exc:  # noqa: BLE001
                logger.info("media utterance force-end failed (%s)", type(exc).__name__)

    @session.on("user_state_changed")
    def _on_user_state(ev) -> None:  # type: ignore[no-untyped-def]
        state.on_user_state(ev.new_state)
        if ev.new_state == "speaking":
            user_started.set()
            if media.playing:
                asyncio.create_task(_set_media_duck(True))
                if _media_utterance_task[0] is not None:
                    _media_utterance_task[0].cancel()
                _media_utterance_task[0] = asyncio.create_task(_force_media_utterance_end())
        elif ev.old_state == "speaking":
            if _media_utterance_task[0] is not None:
                _media_utterance_task[0].cancel()
                _media_utterance_task[0] = None
            asyncio.create_task(_set_media_duck(False))
        policy.touch()
        if ev.old_state == "speaking" and ev.new_state == "listening":
            turns.end_of_speech(ev.created_at)

    @session.on("user_input_transcribed")
    def _on_transcript(ev) -> None:  # type: ignore[no-untyped-def]
        if ev.is_final and ev.transcript.strip():
            if is_system_marker(ev.transcript):
                return
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
        logger.error("session error: %s", type(err).__name__)
        if type(err).__name__ == "STTError":
            message = str(err).casefold()
            if "no speech segment for 60 seconds" in message:
                # LiveKit 1.8.6's STT pipeline retries the stream in-place after a short
                # backoff. Never tear down the job: that invalidates room-bound join links.
                logger.warning("stt stream recreated (idle)")
            else:
                logger.warning("STT error reported; keeping the LiveKit session for stream recovery")

    background: list[asyncio.Task[None]] = []

    @session.on("close")
    def _on_close(ev) -> None:  # type: ignore[no-untyped-def]
        turns.close()
        for task in background:
            task.cancel()

    await session.start(
        room=ctx.room,
        agent=Arjun(turns, responder, state, policy, hold, media, family, user_id, say_locked, call_active),
        room_options=room_io.RoomOptions(text_input=room_io.TextInputOptions(text_input_cb=on_tapped_text)),
    )

    # ---- T8: queued reminders / medicines are spoken here; an idle session closes itself -------------------
    async def claim_next():  # type: ignore[no-untyped-def]
        return await asyncio.to_thread(
            claim_next_delivery, user_id, session_id, None, media.playing, family.present()
        )

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
        policy, quiet=lambda: state.quiet(speech_lock.locked()) and not family.present(), get_busy=get_busy,
        say_closing=say_closing, publish_closed=announce_closed, shutdown=leave,
    )
    background += [asyncio.create_task(deliveries.run()), asyncio.create_task(closer.run())]


if __name__ == "__main__":
    from briefing_audio import start_server

    start_server()
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm, agent_name=AGENT_NAME))
