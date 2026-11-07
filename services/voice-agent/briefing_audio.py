"""Small private OGG/Opus synthesis endpoint, hosted by the voice-agent process."""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
import subprocess
import threading
from typing import get_args

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from livekit import rtc
from livekit.agents import utils
from livekit.plugins import gnani
from livekit.plugins.gnani.models import GnaniTTSModels
from pydantic import BaseModel, Field
from voice import tts_choice

log = logging.getLogger("arjun.briefing_audio")
logging.getLogger("livekit.plugins.gnani").setLevel(logging.CRITICAL)
app = FastAPI(title="Arjun briefing audio", docs_url=None, redoc_url=None)
_lock = asyncio.Lock()
_selection: tuple[str, str] | None = None


class SynthesisIn(BaseModel):
    text: str = Field(min_length=1, max_length=1200)


def _authorized(key: str | None) -> bool:
    expected = os.environ.get("CORE_API_KEY", "")
    return bool(expected and hmac.compare_digest((key or "").encode(), expected.encode()))


async def _select_voice() -> tuple[str, str]:
    """Use the same configured voice when 1.8.6 and this key accept it; else the agent's verified fallback."""
    global _selection
    if _selection:
        return _selection
    choice = tts_choice()
    supported = set(get_args(GnaniTTSModels))  # pinned plugin 1.8.6 exposes v2.0/v2.5 only
    candidates = []
    if choice["model"] in supported:
        candidates.append((choice["model"], choice["voice"]))
    fallback = (choice["fallback_model"], choice["fallback_voice"])
    if fallback[0] in supported and fallback not in candidates:
        candidates.append(fallback)
    for model, voice in candidates:
        probe = gnani.TTS(
            model=model, voice=voice, language=choice["language"], synthesize_method=choice["method"]
        )
        try:
            async with utils.http_context.open():
                await asyncio.wait_for(probe.synthesize("नमस्कार").collect(), timeout=10)
            _selection = (model, voice)
            log.info("briefing TTS ready model=%s", model)
            return _selection
        except Exception as exc:  # never log upstream error bodies or request details
            log.warning("briefing TTS probe failed model=%s error=%s", model, type(exc).__name__)
    raise HTTPException(503, "Timbre synthesis unavailable")


def _frames_to_wav(frames: list[rtc.AudioFrame]) -> bytes:
    if not frames:
        raise ValueError("Timbre returned no audio")
    return rtc.combine_audio_frames(frames).to_wav_bytes()


def _wav_to_ogg(wav: bytes) -> bytes:
    """Encode plugin PCM frames as Telegram-compatible OGG/Opus without writing files."""
    if not wav.startswith(b"RIFF"):
        raise ValueError("Timbre audio is not WAV")
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-c:a", "libopus",
         "-application", "voip", "-b:a", "32k", "-f", "ogg", "pipe:1"],
        input=wav,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.startswith(b"OggS"):
        raise RuntimeError("OGG/Opus encoding failed")
    return result.stdout


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/synthesize")
async def synthesize(body: SynthesisIn, x_api_key: str | None = Header(default=None)) -> Response:
    if not _authorized(x_api_key):
        raise HTTPException(401, "invalid api key")
    async with _lock:
        model, voice = await _select_voice()
        choice = tts_choice()
        synthesizer = gnani.TTS(model=model, voice=voice, language=choice["language"], synthesize_method=choice["method"])
        try:
            async with utils.http_context.open():
                frames = await asyncio.wait_for(synthesizer.synthesize(body.text).collect(), timeout=45)
            wav = await asyncio.to_thread(_frames_to_wav, frames)
            audio = await asyncio.to_thread(_wav_to_ogg, wav)
        except Exception as exc:  # request exception text may contain provider URLs or payload details
            log.warning("briefing TTS request failed model=%s error=%s", model, type(exc).__name__)
            raise HTTPException(502, "Timbre synthesis or OGG/Opus encoding failed") from None
        return Response(audio, media_type="audio/ogg", headers={"X-TTS-Model": model})


def start_server() -> None:
    """Serve only on loopback; scheduler/core-api use this local endpoint."""
    import uvicorn

    threading.Thread(
        target=uvicorn.run,
        kwargs={
            "app": app,
            "host": "127.0.0.1",
            "port": 8002,
            "log_config": None,
            "access_log": False,
        },
        name="briefing-audio",
        daemon=True,
    ).start()
