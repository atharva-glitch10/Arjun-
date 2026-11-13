"""Push-to-record: one whole clip from the elder screen -> Prisma v3 REST -> the normal turn.

The browser records between two taps and sends ONE 16 kHz mono WAV on the LiveKit byte-stream topic "arjun.clip".
Nothing here listens on its own: no VAD, no auto-send. The result goes back as the participant attribute
"arjun.clip" (JSON: id, status, text, lang) so the screen can show her words before Arjun's reply.
"""
from __future__ import annotations

import io
import wave
from dataclasses import dataclass
from typing import Any

from livekit import rtc

TOPIC = "arjun.clip"
ATTRIBUTE = "arjun.clip"
MIN_S = 0.3
MAX_S = 30.0  # matches the browser auto-send cap and Gnani's REST limit

# Said (not sent to the LLM) when nothing was recognised. mr / hi / en only; any other language gets the Marathi line.
EMPTY_LINE = {
    "mr": "ऐकू आलं नाही. बोला दाबून पुन्हा बोला.",
    "hi": "सुनाई नहीं दिया। बोलिए दबाकर फिर से बोलिए।",
    "en": "I didn't catch that. Tap and speak again.",
}


@dataclass
class ClipResult:
    status: str  # heard | too_short | empty | error
    text: str = ""
    lang: str = ""
    seconds: float = 0.0


def empty_line(lang: str | None) -> str:
    return EMPTY_LINE.get(str(lang or "mr").split("-")[0].lower(), EMPTY_LINE["mr"])


def read_wav(data: bytes) -> rtc.AudioFrame | None:
    """The clip as one audio frame, or None if it is not a 16-bit PCM WAV."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            if w.getsampwidth() != 2:
                return None
            rate, chans, pcm = w.getframerate(), w.getnchannels(), w.readframes(w.getnframes())
    except (wave.Error, EOFError):
        return None
    n = len(pcm) // (2 * chans)
    return rtc.AudioFrame(pcm[: n * 2 * chans], rate, chans, n) if n else None


async def process_clip(data: bytes, recognizer: Any) -> ClipResult:
    """`recognizer.recognize([frame])` is the Prisma REST adapter (retries, lock and fallback live there)."""
    frame = read_wav(data)
    if frame is None:
        return ClipResult("too_short") if len(data) <= 44 else ClipResult("error")
    seconds = frame.samples_per_channel / frame.sample_rate
    if seconds < MIN_S:
        return ClipResult("too_short", seconds=seconds)
    if seconds > MAX_S:
        return ClipResult("error", seconds=seconds)
    event = await recognizer.recognize([frame])
    alt = event.alternatives[0] if event.alternatives else None
    text = (alt.text if alt else "").strip()
    lang = str((alt.metadata or {}).get("detected_language_code") or "") if alt else ""
    if text:
        return ClipResult("heard", text, lang, seconds)
    if getattr(recognizer, "last_error", ""):
        return ClipResult("error", seconds=seconds)  # the screen offers a retry
    return ClipResult("empty", seconds=seconds)
