"""Direct Prisma v3 streaming adapter for LiveKit Agents 1.8.6.

Only the documented Vachana websocket protocol is used here. Context values are sent as
recognition bias headers and are never logged or persisted.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import ssl
from functools import lru_cache
from typing import Any

import certifi
import httpx
from livekit import rtc
from livekit.agents import (
    DEFAULT_API_CONNECT_OPTIONS,
    APIConnectionError,
    APIConnectOptions,
    APIStatusError,
    APITimeoutError,
    LanguageCode,
    stt,
    utils,
)
from livekit.agents.types import NOT_GIVEN, NotGivenOr

log = logging.getLogger("arjun.prisma_v3")

REST_URL = "https://api.vachana.ai/stt/v3"
SUPPORTED_LANGS = ("bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "pa-IN", "ta-IN", "te-IN")
AUTO = "indic-auto"
RETRY_LANGS = "mr-IN,hi-IN,en-IN,kn-IN"  # ONLY for the one retry after an empty indic-auto transcript: replaces it, never combined
RETRY_MIN_S = 1.0
MAX_CLIP_S = 30.0
MIN_CLIP_S = 0.3
REST_TIMEOUT_S = 8.0
_warned: set[str] = set()


def _warn_once(key: str, msg: str, *args: Any) -> None:
    if key not in _warned:
        _warned.add(key)
        log.warning(msg, *args)


def clean_language_codes(raw: str | list[str] | None, *, what: str = "GNANI_STT_LANGUAGE_HINTS") -> list[str]:
    """Keep only the 10 supported, case-exact codes (hi-in is a 400), at most 4. Warns once about anything dropped."""
    items = raw if isinstance(raw, list) else str(raw or "").split(",")
    out: list[str] = []
    bad: list[str] = []
    for item in items:
        code = str(item).strip()
        if not code:
            continue
        if code in SUPPORTED_LANGS:
            if code not in out:
                out.append(code)
        else:
            bad.append(code)
    if bad:
        _warn_once(f"{what}:{','.join(bad)}", "%s: dropped unsupported language code(s) %s", what, bad)
    if len(out) > 4:
        _warn_once(f"{what}:cap", "%s: more than 4 codes, keeping the first 4", what)
    return out[:4]


def rest_language_code() -> str:
    """ALWAYS indic-auto: Prisma identifies the language of every utterance (Auto ASR). Never pinned to one locale."""
    return AUTO


def _bounded_values(values: list[str] | None, limit: int) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        value = " ".join(str(value).split())[:80]
        if value and value.casefold() not in seen:
            seen.add(value.casefold())
            output.append(value)
            if len(output) == limit:
                break
    return output


def user_context_terms(user_id: int) -> tuple[list[str], list[str]]:
    """Fetch only recognition bias fields; never include phone numbers, URLs, or free-form facts."""
    base = os.environ.get("CORE_API_URL", "http://127.0.0.1:8000").rstrip("/")
    headers = {"X-API-Key": os.environ["CORE_API_KEY"]} if os.environ.get("CORE_API_KEY") else {}
    try:
        with httpx.Client(base_url=base, headers=headers, timeout=2.0) as client:
            user = client.get(f"/users/{user_id}").json()
            contacts = client.get(f"/users/{user_id}/contacts").json()
            medicines = client.get(f"/users/{user_id}/medicines").json()
            apps = client.get(f"/users/{user_id}/app-links").json()
        terms = [str((user.get("speech_style") or {}).get("companion_name") or "").strip() or "Arjun"]
        terms += list(user.get("interests") or [])
        terms += [row.get("name", "") for row in contacts if isinstance(row, dict)]
        terms += [row.get("name", "") for row in medicines if isinstance(row, dict)]
        for row in apps:
            if isinstance(row, dict):
                terms.append(row.get("label", ""))
                terms.extend(row.get("spoken_names") or [])
        speakers = [row.get("name", "") for row in contacts if isinstance(row, dict)]
        return _bounded_values(terms, 200), _bounded_values(speakers, 4)
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return [], []



@lru_cache(maxsize=1)
def _tls() -> ssl.SSLContext:
    """One TLS context for every Prisma reconnect. Built from the certifi bundle, never from the Windows cert store:
    ssl.create_default_context() with the store blocked the event loop 1.2-1.8 s and timed out the first assignment
    (2026-11-13). Call `warm_tls()` in a thread at worker start so no session ever builds it."""
    return ssl.create_default_context(cafile=certifi.where())


def tls_context() -> ssl.SSLContext:
    """The ONE process-wide TLS context (already built when `warm_tls()` ran at worker start)."""
    return _tls()


def warm_tls() -> ssl.SSLContext:
    """Build the context now (blocking, ~10 ms with certifi): call it from a thread, never from the event loop."""
    return _tls()

class PrismaV3STT(stt.STT):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        sample_rate: int = 16000,
        keyterms: list[str] | None = None,
        speaker_names: list[str] | None = None,
        base_url: str = "wss://api.vachana.ai/stt/v3/stream",
        transport: str | None = None,
        rest_url: str = REST_URL,
    ) -> None:
        if sample_rate not in (8000, 16000, 44100, 48000):
            raise ValueError("Prisma v3 streaming sample rate must be 8000, 16000, 44100, or 48000")
        self.api_key = api_key or os.environ.get("GNANI_API_KEY")
        if not self.api_key:
            raise ValueError("GNANI_API_KEY is required for Prisma v3")
        self.sample_rate = sample_rate
        self.keyterms = _bounded_values(keyterms, 200)
        self.speaker_names = _bounded_values(speaker_names, 4)
        self.base_url = base_url
        self.transport = (transport or os.environ.get("GNANI_STT_TRANSPORT", "ws")).strip().lower()
        if self.transport not in ("ws", "rest"):
            log.warning("GNANI_STT_TRANSPORT=%r is not ws|rest; using ws", self.transport)
            self.transport = "ws"
        self.rest_url = rest_url
        self._rest: RestRecognizer | None = None
        # REST is one request per utterance: not a streaming STT, so AgentSession buffers VAD start..end for us.
        super().__init__(capabilities=stt.STTCapabilities(
            streaming=self.transport == "ws", interim_results=False))

    @property
    def model(self) -> str:
        return "prisma-v3.0"

    @property
    def provider(self) -> str:
        return "Gnani"

    def stream(
        self,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.RecognizeStream:
        del language  # v3 Auto-LID is enabled for every stream.
        return PrismaV3Stream(stt=self, conn_options=conn_options, sample_rate=self.sample_rate)

    async def _recognize_impl(self, *args: Any, **kwargs: Any) -> stt.SpeechEvent:
        if self.transport != "rest":
            raise NotImplementedError("PrismaV3STT supports streaming recognition only (GNANI_STT_TRANSPORT=ws)")
        buffer = args[0] if args else kwargs["buffer"]
        return await self._rest_recognizer().recognize(buffer)

    def _rest_recognizer(self) -> "RestRecognizer":
        if self._rest is None:
            self._rest = RestRecognizer(self)
        return self._rest

    async def warmup(self) -> None:
        """Create the long-lived HTTP client and pre-open TLS so the first utterance pays no handshake."""
        if self.transport == "rest":
            await self._rest_recognizer().warmup()

    async def transcribe_wav(self, wav: bytes, seconds: float) -> tuple[str, str]:
        """Transcribe one complete WAV clip using the same Prisma REST recognizer as the voice session."""
        if self.transport != "rest":
            raise RuntimeError("transcribe_wav requires GNANI_STT_TRANSPORT=rest")
        if not MIN_CLIP_S <= seconds <= MAX_CLIP_S:
            raise ValueError(f"WAV duration must be between {MIN_CLIP_S:.1f} and {MAX_CLIP_S:.0f} seconds")
        recognizer = self._rest_recognizer()
        recognizer.last_error = ""
        try:
            return await recognizer._transcribe(wav, seconds)
        except _Fallback as exc:
            recognizer.last_error = "stt_unavailable"
            raise RuntimeError("Prisma REST request failed after retry") from exc

    async def aclose(self) -> None:
        if self._rest is not None:
            await self._rest.aclose()


DEFAULT_TOPIC = (
    "An elderly Indian person talking at home with a voice companion: daily routine, meals, festivals, family members, "
    "medicine names, reminders, prayers and old songs. Speech may mix Marathi, Hindi and English and may be slow."
)


def stt_topic() -> str:
    raw = os.environ.get("GNANI_STT_TOPIC", "").strip()
    if raw.lower() == "off":
        return ""
    text = raw or DEFAULT_TOPIC
    return text.encode("ascii", "ignore").decode()[:1600]


class PrismaV3Stream(stt.RecognizeStream):
    def __init__(self, *, stt: PrismaV3STT, conn_options: APIConnectOptions, sample_rate: int):
        super().__init__(stt=stt, conn_options=conn_options, sample_rate=sample_rate)
        self._prisma = stt

    async def _run(self) -> None:
        import websockets

        headers = {
            "x-api-key-id": self._prisma.api_key,
            "model": "prisma-v3.0",
            # Auto ASR: language_code is always indic-auto (a comma list is refused on the websocket).
            "language_code": AUTO,
            "format": "codemix",
            "x-sample-rate": str(self._prisma.sample_rate),
        }
        # Gnani `topic` context hint (<= 1,600 chars, fixed per connection): tells Prisma what this audio is about.
        # Plain ASCII only, like every header (GNANI_STT_TOPIC overrides; "off" disables).
        topic = stt_topic()
        if topic:
            headers["topic"] = topic
        if self._prisma.keyterms:
            # Gnani: non-ASCII keyterms JSON must be escaped in headers (raw Devanagari broke the handshake on the laptop).
            headers["keyterms"] = json.dumps(self._prisma.keyterms, ensure_ascii=True)
        if self._prisma.speaker_names:
            headers["speaker_names"] = json.dumps(self._prisma.speaker_names, ensure_ascii=True)
        try:
            tls_context = (
                await asyncio.to_thread(_tls)
                if self._prisma.base_url.startswith("wss:")
                else None
            )
            async with websockets.connect(
                self._prisma.base_url,
                additional_headers=headers,
                ssl=tls_context,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=10,
                open_timeout=self._conn_options.timeout,
            ) as ws:
                raw_first = await asyncio.wait_for(ws.recv(), timeout=10)
                try:
                    first = json.loads(raw_first)
                except (TypeError, ValueError):
                    first = {}
                if first.get("type") != "connected":
                    # Say WHY (Gnani's own message, never our headers/key) so the log is actionable.
                    reason = str(first.get("message") or first.get("error") or first.get("type") or raw_first)[:200]
                    raise APIConnectionError(f"Prisma v3 stream did not confirm connection: {reason}")
                sender = asyncio.create_task(self._send_audio(ws))
                receiver = asyncio.create_task(self._receive(ws))
                try:
                    done, _ = await asyncio.wait((sender, receiver), return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
                    if sender.done() and not receiver.done():
                        try:
                            await asyncio.wait_for(asyncio.shield(receiver), timeout=1.0)
                        except asyncio.TimeoutError:
                            pass
                finally:
                    await utils.aio.gracefully_cancel(sender, receiver)
        except asyncio.CancelledError:
            raise
        except websockets.exceptions.ConnectionClosed as exc:
            raise APIConnectionError("Prisma v3 websocket closed") from exc
        except asyncio.TimeoutError as exc:
            raise APITimeoutError("Prisma v3 websocket timed out") from exc
        except (APIConnectionError, APIStatusError, APITimeoutError):
            raise
        except Exception as exc:
            raise APIConnectionError("Prisma v3 websocket failed") from exc

    async def _send_audio(self, ws: Any) -> None:
        audio_buffer = bytearray()
        async for item in self._input_ch:
            if isinstance(item, self._FlushSentinel):
                if audio_buffer:
                    audio_buffer.extend(bytes(1024 - len(audio_buffer)))
                    await ws.send(bytes(audio_buffer))
                    audio_buffer.clear()
                await ws.send('{"type":"commit"}')
            else:
                frame: rtc.AudioFrame = item
                audio_buffer.extend(frame.data.tobytes())
                while len(audio_buffer) >= 1024:
                    await ws.send(bytes(audio_buffer[:1024]))
                    del audio_buffer[:1024]
                    await asyncio.sleep(512 / self._prisma.sample_rate)
        if audio_buffer:
            audio_buffer.extend(bytes(1024 - len(audio_buffer)))
            await ws.send(bytes(audio_buffer))

    async def _receive(self, ws: Any) -> None:
        async for msg in ws:
            if isinstance(msg, bytes):
                continue
            data = json.loads(msg)
            kind = data.get("type")
            if kind == "transcript" and data.get("text"):
                lang = str(data.get("detected_language_code") or "en")
                try:
                    language = LanguageCode(lang)
                except ValueError:
                    language = LanguageCode("en")
                self._event_ch.send_nowait(stt.SpeechEvent(
                    type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                    request_id=str(data.get("segment_id") or ""),
                    alternatives=[stt.SpeechData(
                        language=language,
                        text=str(data["text"]),
                        confidence=float(data.get("confidence") or 1.0),
                        metadata={"detected_language_code": lang},
                    )],
                ))
            elif kind in ("speech_start", "vad_start"):
                self._event_ch.send_nowait(stt.SpeechEvent(type=stt.SpeechEventType.START_OF_SPEECH))
            elif kind in ("speech_end", "vad_end"):
                self._event_ch.send_nowait(stt.SpeechEvent(type=stt.SpeechEventType.END_OF_SPEECH))
            elif kind == "error":
                raise APIStatusError("Prisma v3 stream returned an error", status_code=500)


# ---------------------------------------------------------------- REST transport (one request per utterance)

_FIXED_KEYTERMS = ["Arjun", "BP", "sugar", "blood pressure", "tablet", "medicine", "reminder"]


def build_keyterms(keyterms: list[str] | None) -> list[str]:
    return _bounded_values(list(keyterms or []) + _FIXED_KEYTERMS, 50)


class _Fallback(Exception):
    """The REST attempt is exhausted; use WS for this one utterance."""


class RestRecognizer:
    def __init__(self, owner: PrismaV3STT) -> None:
        self.o = owner
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()  # Gnani: ONE active request per account
        self.last_error = ""  # set when the last recognize() could not reach a transcript (not when it was just silence)
        self._prev: list[str] = []

    async def warmup(self) -> None:
        client = await self._get_client()
        try:
            await client.get(self.o.rest_url.rsplit("/stt/", 1)[0] + "/")  # TLS pre-connect; any status is fine
        except httpx.HTTPError:
            pass

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            ctx = await asyncio.to_thread(_tls)  # loading the CA bundle blocks ~100 ms
            self._client = httpx.AsyncClient(
                http2=False, verify=ctx, timeout=REST_TIMEOUT_S,
                headers={"X-API-Key-ID": self.o.api_key or ""})
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def _clips(buffer: Any) -> list[tuple[bytes, float]]:
        """Merge the VAD frames, cut into <= 30 s pieces, wrap each as an in-memory WAV."""
        frame = utils.merge_frames(buffer) if isinstance(buffer, list) else buffer
        rate, chans = frame.sample_rate, frame.num_channels
        data = bytes(frame.data)
        width = 2 * chans
        total = len(data) // width
        step = int(MAX_CLIP_S * rate)
        clips = []
        for start in range(0, total, step):
            piece = data[start * width:min(total, start + step) * width]
            n = len(piece) // width
            clips.append((rtc.AudioFrame(piece, rate, chans, n).to_wav_bytes(), n / rate))
        return clips

    def _fields(self, language_code: str) -> dict[str, str]:
        fields = {"model": "prisma-v3.0", "language_code": language_code,
                  "format": os.environ.get("GNANI_STT_FORMAT", "transcribe").strip() or "transcribe"}
        topic = stt_topic()
        if topic:
            fields["topic"] = topic
        fields["keyterms"] = json.dumps(build_keyterms(self.o.keyterms))
        if os.environ.get("GNANI_STT_PREV_TEXT", "0") == "1" and self._prev:
            fields["previous_text"] = " ".join(self._prev[-2:])[-600:]
        return fields

    async def _post(self, wav: bytes, language_code: str) -> httpx.Response:
        client = await self._get_client()
        async with self._lock:  # one request in flight, ever
            return await client.post(
                self.o.rest_url, data=self._fields(language_code),
                files={"audio_file": ("utterance.wav", wav, "audio/wav")})

    @staticmethod
    def _err(resp: httpx.Response) -> str:
        """error.type / detail only; never the request, headers or key."""
        try:
            body = resp.json()
        except ValueError:
            return f"http {resp.status_code}"
        if isinstance(body, dict):
            e = body.get("error")
            if isinstance(e, dict):
                return f"{e.get('type')}: {str(e.get('message'))[:120]}"
            d = body.get("detail")
            if isinstance(d, dict):
                return str(d.get("error_code"))
            if isinstance(d, list):
                return "; ".join(str(x.get("msg")) for x in d[:3] if isinstance(x, dict))
            if body.get("code"):
                return str(body["code"])
        return f"http {resp.status_code}"

    async def _request(self, wav: bytes, language_code: str) -> dict | None:
        """200 -> JSON. Other 4xx -> None (no retry). 429 / 5xx / timeout -> one retry, then _Fallback."""
        retried = False
        while True:
            status, resp, problem = 0, None, ""
            try:
                resp = await self._post(wav, language_code)
                status = resp.status_code
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                problem = type(exc).__name__
            if resp is not None and status == 200:
                try:
                    return resp.json()
                except ValueError:
                    problem = "bad json"
            elif resp is not None and 400 <= status < 500 and status != 429:
                log.error("prisma rest %s: %s (not retried)", status, self._err(resp))
                self.last_error = f"http_{status}"
                return None
            elif resp is not None:
                problem = f"{status} {self._err(resp)}"
            if retried:
                log.warning("prisma rest failed twice (%s); websocket fallback for this utterance", problem)
                raise _Fallback(problem)
            retried = True
            log.info("prisma rest retry (%s)", problem)
            if status == 429:
                await asyncio.sleep(0.4)

    async def _transcribe(self, wav: bytes, seconds: float) -> tuple[str, str]:
        language, reason = rest_language_code(), "none"
        data = await self._request(wav, language)
        text = str((data or {}).get("transcript") or "").strip()
        if not text and data is not None and seconds >= RETRY_MIN_S and language == AUTO:
            reason = "empty transcript with indic-auto -> language list"
            language = RETRY_LANGS  # replaces indic-auto for this one retry
            log.info("prisma rest: %s (%s)", reason, language)
            data = await self._request(wav, language)
            text = str((data or {}).get("transcript") or "").strip()
        data = data or {}
        detected = str(data.get("detected_language_code") or "")
        if detected and detected not in SUPPORTED_LANGS:
            log.info("prisma rest: detected language %s is outside the supported set (kept)", detected)
        if data.get("truncated"):
            log.warning("prisma rest: transcript truncated by Gnani; using the text we got")
        log.info("prisma stt transport=rest language_code=%s detected=%s audio_s=%.2f processing_time=%s "
                 "end_to_end_latency=%s retry=%s empty=%s", language, detected or "-", seconds,
                 data.get("processing_time"), data.get("end_to_end_latency"), reason, not text)
        return text, detected

    async def _ws_once(self, wav: bytes) -> tuple[str, str]:
        """One-shot websocket for a single utterance, used only when REST is exhausted. UNVERIFIED live."""
        import websockets

        pcm = wav[44:]
        headers = {"x-api-key-id": self.o.api_key, "model": "prisma-v3.0", "language_code": AUTO,
                   "format": "codemix", "x-sample-rate": str(self.o.sample_rate)}
        text, lang = "", ""
        tls_context = await asyncio.to_thread(_tls)
        async with websockets.connect(self.o.base_url, additional_headers=headers, ssl=tls_context,
                                      open_timeout=REST_TIMEOUT_S) as ws:
            await asyncio.wait_for(ws.recv(), timeout=10)
            for i in range(0, len(pcm), 1024):
                await ws.send(pcm[i:i + 1024].ljust(1024, b"\0"))
            await ws.send('{"type":"commit"}')
            try:
                async with asyncio.timeout(REST_TIMEOUT_S):
                    async for msg in ws:
                        if isinstance(msg, bytes):
                            continue
                        data = json.loads(msg)
                        if data.get("type") == "transcript" and data.get("text"):
                            text, lang = str(data["text"]), str(data.get("detected_language_code") or "")
                            break
            except TimeoutError:
                pass
        return text, lang

    async def recognize(self, buffer: Any) -> stt.SpeechEvent:
        self.last_error = ""
        texts: list[str] = []
        lang = ""
        for wav, seconds in self._clips(buffer):
            if seconds < MIN_CLIP_S:
                log.info("prisma rest: clip %.2fs < %.1fs skipped", seconds, MIN_CLIP_S)
                continue
            try:
                text, detected = await self._transcribe(wav, seconds)
            except _Fallback:
                try:
                    text, detected = await self._ws_once(wav)
                    log.info("prisma stt transport=ws(fallback) detected=%s audio_s=%.2f", detected or "-", seconds)
                except Exception as exc:  # noqa: BLE001 - empty transcript, never a crash
                    log.error("prisma websocket fallback failed: %s", type(exc).__name__)
                    self.last_error = "stt_unavailable"
                    text, detected = "", ""
            if text:
                texts.append(text)
            lang = detected or lang
        joined = " ".join(texts)
        if joined:
            self._prev = (self._prev + [joined])[-2:]
        try:
            language = LanguageCode(lang or "en")
        except ValueError:
            language = LanguageCode("en")
        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT, request_id="",
            alternatives=[stt.SpeechData(language=language, text=joined, confidence=1.0,
                                         metadata={"detected_language_code": lang})])
