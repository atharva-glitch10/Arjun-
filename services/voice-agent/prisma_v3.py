"""Direct Prisma v3 streaming adapter for LiveKit Agents 1.8.6.

Only the documented Vachana websocket protocol is used here. Context values are sent as
recognition bias headers and are never logged or persisted.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

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
        terms = list(user.get("interests") or [])
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


class PrismaV3STT(stt.STT):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        sample_rate: int = 16000,
        keyterms: list[str] | None = None,
        speaker_names: list[str] | None = None,
        language_hints: list[str] | None = None,
        base_url: str = "wss://api.vachana.ai/stt/v3/stream",
    ) -> None:
        if sample_rate not in (8000, 16000, 44100, 48000):
            raise ValueError("Prisma v3 streaming sample rate must be 8000, 16000, 44100, or 48000")
        self.api_key = api_key or os.environ.get("GNANI_API_KEY")
        if not self.api_key:
            raise ValueError("GNANI_API_KEY is required for Prisma v3")
        self.sample_rate = sample_rate
        self.keyterms = _bounded_values(keyterms, 200)
        self.speaker_names = _bounded_values(speaker_names, 4)
        self.language_hints = _bounded_values(language_hints, 4)
        self.base_url = base_url
        super().__init__(capabilities=stt.STTCapabilities(streaming=True, interim_results=False))

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
        raise NotImplementedError("PrismaV3STT supports streaming recognition only")

    async def aclose(self) -> None:
        return None


class PrismaV3Stream(stt.RecognizeStream):
    def __init__(self, *, stt: PrismaV3STT, conn_options: APIConnectOptions, sample_rate: int):
        super().__init__(stt=stt, conn_options=conn_options, sample_rate=sample_rate)
        self._prisma = stt

    async def _run(self) -> None:
        import websockets

        headers = {
            "x-api-key-id": self._prisma.api_key,
            "model": "prisma-v3.0",
            "language_code": ",".join(self._prisma.language_hints) if self._prisma.language_hints else "indic-auto",
            "format": "codemix",
            "x-sample-rate": str(self._prisma.sample_rate),
        }
        if self._prisma.keyterms:
            headers["keyterms"] = json.dumps(self._prisma.keyterms, ensure_ascii=False)
        if self._prisma.speaker_names:
            headers["speaker_names"] = json.dumps(self._prisma.speaker_names, ensure_ascii=False)
        try:
            async with websockets.connect(
                self._prisma.base_url,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=10,
                open_timeout=self._conn_options.timeout,
            ) as ws:
                first = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                if first.get("type") != "connected":
                    raise APIConnectionError("Prisma v3 stream did not confirm connection")
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
