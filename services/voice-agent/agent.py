"""LiveKit Agents worker: Gnani Prisma (STT) + Gnani Timbre (TTS), reasoning over HTTP.

STATUS: TTS verified live through the plugin (2026-10-21). A full spoken turn has NOT yet run
end to end (T4). No LLM is configured: every reply is the templated text returned by reasoning
/turn. Dispatch is EXPLICIT: the worker registers as AGENT_NAME ("arjun") and only joins rooms whose
token/room config dispatches that name (see scripts/make_token.py). The tested logic is in bridge.py.
"""

import asyncio
import logging
import os
import re
import sys
import time
from pathlib import Path

import aiohttp
import applog
import clonedvoice
import httpx
import voiceprovider
from audiowarm import warm_audio_resampler
from bridge import (
    claim_next_delivery,
    closing_text,
    mark_delivery_spoken,
    release_delivery,
    reply_or_fallback,
    report_sound_event,
    session_busy,
)
from bridge import media_stopped as notify_media_stopped
from bridge import video_call_stopped as notify_video_call_stopped
from delivery import DeliveryLoop
from dotenv import dotenv_values
from endpointing import (
    ConjunctionHold,
    EndpointingPolicy,
    turn_detection_from_env,
    turn_handling_options,
)
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
    utils,
)
from livekit.agents import tts as lk_tts
from livekit.plugins import gnani, silero

try:  # TESTING switch (voiceprovider.py). Imported here: a plugin must be registered on the main thread.
    from livekit.plugins import sarvam
except ImportError:  # the Gnani path does not need it
    sarvam = None
from livekit.plugins.gnani.tts import (
    RESTChunkedStream,
    SSEChunkedStream,
    _build_headers,
    _build_payload,
    _mime_type,
)
from media import (
    ATTR_MEDIA,
    ATTR_VIDEO_CALL,
    MediaState,
    is_bare_control,
    is_system_marker,
    should_send,
    strip_wake_word,
)
from prisma_v3 import PrismaV3STT, user_context_terms
from responder import Responder
from safety_words import is_safety_phrase
from screenstate import publish_closed, publish_delivery, publish_screen, publish_thinking
from sessionstate import SessionState
from soundevents import (
    OnnxYamnet,
    SoundCheckWindow,
    SoundEvent,
    SoundEventAudioInput,
    SoundEventMonitor,
)
from soundevents import (
    enabled as sound_events_enabled,
)
from ttsgate import TtsGate
from turnlog import TurnLog
from usermeta import user_id_from_metadata
from voice import (
    slower_text,
    strip_tags,
    stt_options,
    tts_choice,
    tts_language_for,
    tts_text,
    tts_voice_for,
)

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
STT_OPTIONS = stt_options() if os.environ.get("GNANI_STT_IMPL", "plugin").strip().lower() == "plugin" else {}
# Explicit dispatch name. An unnamed worker was never sent into Console/Playground rooms (2026-10-21).
AGENT_NAME = os.environ.get("ARJUN_AGENT_NAME", "arjun")
# Seconds of silence before end of turn: mode-aware since task D (2026-10-31), see endpointing.py. Care 0.8 / 2.5 s,
# companion / story 1.6 / 4.0 s, chosen by the mode of the LAST reply. PLACEHOLDERS until tuned on real elderly speech.


TTS_GATE = TtsGate()  # Timbre allows ONE active request at a time (429 RATE_LIMITED otherwise); see ttsgate.py


def _fetch_user_languages(user_id: int) -> dict:
    base = os.environ.get("CORE_API_URL", "http://127.0.0.1:8000").rstrip("/")
    headers = {"X-API-Key": os.environ["CORE_API_KEY"]} if os.environ.get("CORE_API_KEY") else {}
    response = httpx.get(f"{base}/users/{user_id}", headers=headers, timeout=2.0)
    response.raise_for_status()
    return response.json()


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


async def tts_audio(tts_obj, text: str):  # type: ignore[no-untyped-def]
    """Synthesize `text` with a specific TTS and yield its audio frames.

    LiveKit Agents 1.8.6 `AgentSession.say()` has NO `tts=` argument (it raised TypeError, so every reply that
    picked a per-language or cloned voice was silent). It does take `audio=`: we synthesize with the chosen TTS here
    and hand the frames over, so the text and the voice stay exactly what we chose."""
    async with tts_obj.synthesize(text) as stream:
        async for ev in stream:
            yield ev.frame


class _ClonedRest(RESTChunkedStream):
    """Gnani Voice Cloned TTS REST (POST /api/v1/tts/inference with speaker_embedding), one request at a time."""

    async def _run(self, output_emitter) -> None:  # type: ignore[no-untyped-def]
        async def once() -> None:
            payload = clonedvoice.cloned_payload(_build_payload(self._opts, self._input_text), self._tts.cloned)
            async with self._tts._ensure_session().post(
                url=f"{self._opts.base_url}/api/v1/tts/inference", json=payload, headers=_build_headers(self._opts),
                timeout=aiohttp.ClientTimeout(total=self._conn_options.timeout),
            ) as res:
                if res.status != 200:
                    raise APIStatusError(message=f"Gnani cloned TTS error {res.status}", status_code=res.status,
                                         body=(await res.text())[:200])
                audio = await res.read()
                output_emitter.initialize(request_id=utils.shortuuid(), sample_rate=self._tts.sample_rate,
                                          num_channels=self._tts.num_channels, mime_type=_mime_type(self._opts))
                output_emitter.push(audio)
                output_emitter.flush()

        await TTS_GATE.run(once, _timbre_busy)


class _ClonedSse(RESTChunkedStream):
    """Gnani Voice Cloned TTS streaming (POST /api/v1/tts/sse, vachana-vc-v1 + speaker_embedding): audio is pushed
    chunk by chunk, so the familiar voice starts speaking without waiting for the whole file. One request at a time."""

    async def _run(self, output_emitter) -> None:  # type: ignore[no-untyped-def]
        async def once() -> None:
            payload = clonedvoice.cloned_payload(_build_payload(self._opts, self._input_text), self._tts.cloned)
            async with self._tts._ensure_session().post(
                url=f"{self._opts.base_url}/api/v1/tts/sse", json=payload, headers=_build_headers(self._opts),
                timeout=aiohttp.ClientTimeout(total=self._conn_options.timeout), read_bufsize=10 * 1024 * 1024,
            ) as res:
                if res.status != 200:
                    raise APIStatusError(message=f"Gnani cloned TTS SSE error {res.status}", status_code=res.status,
                                         body=(await res.text())[:200])
                output_emitter.initialize(request_id=utils.shortuuid(), sample_rate=self._tts.sample_rate,
                                          num_channels=self._tts.num_channels, mime_type=_mime_type(self._opts))
                parser = clonedvoice.SseParser()
                async for raw in res.content:
                    for chunk in parser.feed(raw.decode("utf-8")):
                        output_emitter.push(chunk)
                    if parser.done:
                        break
                output_emitter.flush()

        try:
            await TTS_GATE.run(once, _timbre_busy)
        except clonedvoice.SseError as exc:
            raise APIStatusError(message=f"Gnani cloned TTS SSE error: {exc}", status_code=500, body=str(exc)) from exc


class ClonedTimbre(gnani.TTS):
    """Speaks one companion reply in the family-approved cloned voice (consent recorded in core-api)."""

    def __init__(self, cloned: "clonedvoice.ClonedVoice", **kw) -> None:  # type: ignore[no-untyped-def]
        super().__init__(synthesize_method="rest", **kw)
        self.cloned = cloned
        self._capabilities = lk_tts.TTSCapabilities(streaming=False)

    def synthesize(self, text, *, conn_options=DEFAULT_API_CONNECT_OPTIONS):  # type: ignore[no-untyped-def]
        stream = _ClonedRest if clonedvoice.METHOD == "rest" else _ClonedSse
        return stream(tts=self, input_text=text, conn_options=conn_options)


def make_tts(model: str, voice: str, language: str | None = None):  # type: ignore[no-untyped-def]
    kw = {"model": model, "voice": voice, "language": language or TTS_LANGUAGE}
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
        media: MediaState, family: FamilyPresence, user_id: int, event_say, call_active, transcript_languages,
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
        self.transcript_languages = transcript_languages
        # No LLM on the session; instructions are unused but required by the base class.
        super().__init__(instructions="Arjun is an AI voice companion. Replies come from reasoning.")

    async def _answer_held_later(self, held: str) -> None:
        await asyncio.sleep(HELD_ANSWER_S)
        if not held or self.hold.held != held:  # a later turn already took (or replaced) it
            return
        self.hold.held = ""
        vlog("held turn answered after %.1f s with no more words (%d chars)", HELD_ANSWER_S, len(held))
        async with self.state.turn():
            await self.responder.respond(held, "voice")
        self.policy.touch()

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
            if text is None:
                vlog("turn held for more speech (%d chars)", len(transcript))
                # If the rest never becomes words (noise, a cough, Prisma returns nothing), the held part would never
                # be answered. Answer it ourselves once nothing new has arrived for HELD_ANSWER_S.
                held = self.hold.held
                asyncio.create_task(self._answer_held_later(held))
            raise StopResponse()
        t0 = time.monotonic()
        vlog("turn -> reasoning (%d chars)", len(text))
        async with self.state.turn():  # while a spoken turn is being answered the session is not idle / quiet
            await self.responder.respond(text, "voice")
        vlog("turn answered in %d ms", int((time.monotonic() - t0) * 1000))
        self.policy.touch()
        raise StopResponse()  # suppress the default LLM reply


# One short line per step of a spoken turn (speech heard, STT result, reasoning, reply voice) so a silent Arjun can be
# diagnosed from logs/voice-agent.app.log. Never the words: only lengths, language, timings. ARJUN_DEBUG_VOICE=0 = off.
DEBUG_VOICE = os.environ.get("ARJUN_DEBUG_VOICE", "1").strip() != "0"
# A held (unfinished-sounding) sentence is answered after this many seconds if no further words arrive.
HELD_ANSWER_S = float(os.environ.get("ARJUN_HELD_ANSWER_S", "4.0") or 4.0)


def vlog(msg: str, *args: object) -> None:
    if DEBUG_VOICE:
        logger.info("voice: " + msg, *args)


def prewarm(proc: agents.JobProcess) -> None:
    """Once per job process, before any session: warm the resampler and load the VAD model."""
    warm_audio_resampler()
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: agents.JobContext) -> None:
    warm_audio_resampler()  # idempotent, a safety net
    applog.setup_file_log() # the CLI may have reset logging after import; make sure the file handler is on
    await ctx.connect()
    from_metadata = user_id_from_metadata(ctx.job.metadata, 0)
    user_id = from_metadata or USER_ID
    use_sarvam = voiceprovider.provider() == "sarvam"  # TESTING switch; the default is the Gnani path below
    if use_sarvam:
        stt_plugin, tts_plugin = voiceprovider.make_sarvam(sarvam)
        active_model = voiceprovider.TTS_MODEL  # not a Timbre tag model: <tags> are stripped
        logger.info(voiceprovider.start_line())  # no Timbre probe
    else:
        tts_plugin, active_model = await working_tts()  # Timbre v3.0 over SSE, or the verified fallback
        stt_impl = os.environ.get("GNANI_STT_IMPL", "plugin").strip().lower()
        vlog("stt implementation: %s", stt_impl)
        if stt_impl not in {"plugin", "v3"}:
            raise ValueError("GNANI_STT_IMPL must be plugin or v3")
        if stt_impl == "v3":
            sample_rate = int(os.environ.get("GNANI_STT_SAMPLE_RATE", "16000"))
            keyterms, speakers = await asyncio.to_thread(user_context_terms, user_id)
            try:
                user = await asyncio.to_thread(_fetch_user_languages, user_id)
                language_hints = [f"{code}-IN" for code in (user.get("preferred_languages") or [user.get("language", "mr")])]
            except Exception:
                language_hints = []
            stt_plugin = PrismaV3STT(
                sample_rate=sample_rate, keyterms=keyterms, speaker_names=speakers, language_hints=language_hints,
            )
            logger.info("voice provider: gnani (stt prisma-v3.0, tts %s)", active_model)
        else:
            stt_plugin = gnani.STT(use_streaming=USE_STREAMING, **STT_OPTIONS)
            logger.info("voice provider: gnani (stt prisma plugin, tts %s)", active_model)
        logger.info("stt stream recreated: fresh Gnani STT instance for voice session")
        logger.info("TTS %s via %s; STT implementation %s", active_model, TTS["method"],
                    os.environ.get("GNANI_STT_IMPL", "plugin"))
    endpointing = EndpointingPolicy()  # starts in care timing; each reply's mode sets the next turn's
    handling: dict = turn_handling_options()  # type: ignore[assignment]
    detection = turn_detection_from_env()  # "vad" by default; None = LiveKit's cloud detector (see endpointing.py)
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
    logger.info("session serves user %s (%s)", user_id, "dispatch metadata" if from_metadata else "ARJUN_USER_ID fallback")

    async def ask(text: str):  # type: ignore[no-untyped-def]
        normalized = " ".join(text.casefold().split())
        matching = [
            (len(key), value) for key, value in transcript_languages.items()
            if key != "__current__" and key and key in normalized
        ]
        detected = max(matching)[1] if matching else transcript_languages.get("__current__", STT_LANGUAGE)
        return await asyncio.to_thread(reply_or_fallback, user_id, text, detected)

    async def say_reply(reply) -> bool:  # type: ignore[no-untyped-def]
        """Synthesize this reply in Prisma's detected language using the verified session model/voice."""
        detected = reply.language or transcript_languages.get("__current__", STT_LANGUAGE)
        language = tts_language_for(detected, TTS_LANGUAGE)
        voice = TTS_VOICE if active_model == TTS_MODEL else TTS["fallback_voice"]
        voice = tts_voice_for(detected, language, voice)
        plugin = make_tts(active_model, voice, language)
        text = tts_text(reply.text, reply.speech, active_model)
        if (reply.speech_style or {}).get("rate") == "slow":
            text = slower_text(text)
        # Off the event loop: the lookup is a (cached) HTTP call and must never stall live audio.
        cloned = (
            await asyncio.to_thread(cloned_voices.get)
            if not use_sarvam and clonedvoice.allowed(reply) and clonedvoice.language_allowed(detected)
            else None
        )
        vlog("reply voice: %s (%d chars)", f"cloned {cloned.name}" if cloned else active_model, len(text))
        async with speech_lock:
            before = state.speaking_count
            if cloned is not None:
                # Familiar voice for companion talk only; plain text (Timbre v3 emotion tags are not for VC).
                plain = strip_tags(reply.speech or reply.text)
                cloned_tts = ClonedTimbre(cloned, model=TTS["fallback_model"], voice=TTS["fallback_voice"])
                handle = session.say(plain, audio=tts_audio(cloned_tts, plain))
                await handle
                spoke = state.speaking_count > before
                if handle.interrupted:  # she started talking: that is a real turn, not a failure
                    return False
                if handle.exception() is None and spoke:
                    asyncio.get_running_loop().run_in_executor(None, clonedvoice.report_used, user_id, cloned.voice_id)
                    return True
                # An error OR silence (no audio played, no exception) both fall back, so Arjun is never mute.
                cause = type(handle.exception()).__name__ if handle.exception() is not None else "no audio"
                logger.warning("cloned voice synthesis failed (%s); speaking as Arjun", cause)
                cloned_voices.forget()
                before = state.speaking_count
            handle = session.say(text, audio=tts_audio(plugin, text))
            await handle
            return not handle.interrupted and handle.exception() is None and state.speaking_count > before

    cloned_voices = clonedvoice.VoiceSource(user_id)  # family-approved voice, re-checked every minute
    state = SessionState()
    policy = IdlePolicy()
    speech_lock = asyncio.Lock()  # one line at a time: a reply, a reminder and the closing line never overlap
    session_id = ctx.job.id

    async def say_locked(text: str) -> None:
        async with speech_lock:
            detected = transcript_languages.get("__current__", TTS_LANGUAGE)
            language = tts_language_for(detected, TTS_LANGUAGE)
            voice = tts_voice_for(detected, language, TTS_VOICE if active_model == TTS_MODEL else TTS["fallback_voice"])
            plugin = make_tts(active_model, voice, language)
            await session.say(text, audio=tts_audio(plugin, text))

    sound_check_task: list[asyncio.Task[None] | None] = [None]
    sound_monitor: list[SoundEventMonitor | None] = [None]
    sound_check = SoundCheckWindow()

    async def handle_sound_event(event: SoundEvent) -> None:
        if not event.check_in:
            await asyncio.to_thread(report_sound_event, user_id, event.label, event.confidence)
        if event.label == "crying" and not event.check_in:
            if not family.present():
                await say_locked("तुम्हाला बोलावंसं वाटतंय का? मी ऐकायला आहे.")
            return
        if not event.check_in or event.label not in {"scream", "bang"} or family.present():
            return
        previous = sound_check_task[0]
        if previous is not None and not previous.done():
            return

        async def ask_and_escalate() -> None:
            sound_check.start(time.monotonic())
            user_started.clear()
            await say_locked("तुम्ही ठीक आहात का?")
            if state.user == "speaking":  # speech during the prompt counts as an answer
                sound_check.answered()
                return
            try:
                await asyncio.wait_for(user_started.wait(), timeout=20.0)
            except asyncio.TimeoutError:
                if sound_check.should_escalate(time.monotonic()) and state.user != "speaking" and not family.present():
                    logger.warning("sound event check-in unanswered; emergency flow started")
                    await asyncio.to_thread(report_sound_event, user_id, event.label, event.confidence, escalate=True)

        sound_check_task[0] = asyncio.create_task(ask_and_escalate(), name="sound-event-check-in")

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
        thinking=lambda on: publish_thinking(ctx.room.local_participant, on),  # "विचार करतोय…"
        speakable=lambda reply: voiceprovider.sarvam_text(speakable_text(reply)) if use_sarvam else speakable_text(reply),
        say_reply=None if use_sarvam else say_reply,
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
        vlog("user %s -> %s", ev.old_state, ev.new_state)
        state.on_user_state(ev.new_state)
        if ev.new_state == "speaking":
            sound_check.answered()
            turns.user_started_speaking(ev.created_at)
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
            if DEBUG_VOICE:
                asyncio.create_task(_warn_if_no_transcript(stt_finals[0]))

    transcript_languages: dict[str, str] = {}
    stt_heard = [False]  # an interim was already logged for the current utterance
    stt_finals = [0]  # count of final transcripts, to catch "speech detected but STT said nothing"

    async def _warn_if_no_transcript(finals_before: int) -> None:
        await asyncio.sleep(4.0)
        if stt_finals[0] == finals_before:
            logger.warning(
                "voice: speech was detected but Prisma returned no words within 4 s. Check GNANI_API_KEY is valid, "
                "try GNANI_STT_IMPL=v3 (auto language), and that the right microphone is selected in Chrome."
            )

    @session.on("user_input_transcribed")
    def _on_transcript(ev) -> None:  # type: ignore[no-untyped-def]
        if ev.is_final:
            stt_finals[0] += 1
            vlog("stt final: %d chars, language %s", len(ev.transcript.strip()), ev.language or "?")
        elif not stt_heard[0]:
            vlog("stt interim: speech is being recognised")
        stt_heard[0] = not ev.is_final
        if ev.is_final and ev.transcript.strip():
            if is_system_marker(ev.transcript):
                return
            if ev.language:
                code = str(ev.language)
                transcript_languages["__current__"] = code
                transcript_languages[" ".join(ev.transcript.casefold().split())] = code
                if len(transcript_languages) > 33:
                    oldest = next((key for key in transcript_languages if key != "__current__"), None)
                    if oldest:
                        transcript_languages.pop(oldest, None)
            turns.final_transcript(ev.created_at, ev.transcript, str(ev.language) if ev.language else None)

    @session.on("agent_state_changed")
    def _on_agent_state(ev) -> None:  # type: ignore[no-untyped-def]
        vlog("arjun %s -> %s", ev.old_state, ev.new_state)
        state.on_agent_state(ev.new_state)
        if ev.old_state == "speaking" and ev.new_state != "speaking":
            turns.agent_stopped_speaking(ev.created_at)
        policy.touch()  # the 60 s idle clock starts when Arjun stops talking
        if ev.new_state == "speaking":
            turns.agent_speaking(ev.created_at)

    @session.on("error")
    def _on_error(ev) -> None:  # type: ignore[no-untyped-def]
        # STT / TTS / plugin failures: type and a short message only (never headers or keys).
        err = getattr(ev, "error", ev)
        logger.error("session error: %s", type(err).__name__)
        # The provider's own reason (status/message), never headers or keys: says WHY STT/TTS failed.
        vlog("error detail: %s", re.sub(r"(vach_|sk_|AQ\.|AIza)[\w\-.]+", r"\1<hidden>", " ".join(str(err).split()))[:200])
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
        if sound_monitor[0] is not None:
            sound_monitor[0].close()
        if sound_check_task[0] is not None:
            sound_check_task[0].cancel()
        for task in background:
            task.cancel()

    await session.start(
        room=ctx.room,
        agent=Arjun(turns, responder, state, policy, hold, media, family, user_id, say_locked, call_active,
                    transcript_languages),
        room_options=room_io.RoomOptions(text_input=room_io.TextInputOptions(text_input_cb=on_tapped_text)),
    )

    if sound_events_enabled():
        model_path = os.environ.get("ARJUN_SOUND_MODEL_PATH", "").strip()
        try:
            if not model_path:
                raise FileNotFoundError("ARJUN_SOUND_MODEL_PATH is empty")
            event_loop = asyncio.get_running_loop()
            sound_monitor[0] = SoundEventMonitor(
                await asyncio.to_thread(OnnxYamnet, model_path),
                lambda event: event_loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(handle_sound_event(event))
                ),
            )
            if session.input.audio is not None:
                session.input.audio = SoundEventAudioInput(session.input.audio, sound_monitor[0])
                logger.info("sound events enabled (ONNX CPU, bounded worker)")
            else:
                sound_monitor[0].close()
                sound_monitor[0] = None
                logger.warning("sound events skipped: session has no audio input")
        except Exception as exc:  # noqa: BLE001 - missing/invalid optional model must not stop voice service
            logger.warning("sound events skipped (%s)", type(exc).__name__)

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
