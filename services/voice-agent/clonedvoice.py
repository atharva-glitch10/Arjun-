"""Consent-first cloned voice for companion chat (Gnani Voice Cloned TTS, docs.gnani.ai/api/VC).

The family adds a voice on the dashboard (core-api voices.py, consent recorded, embedding encrypted). This module
decides WHEN that voice may speak and fetches it. Pure functions + a small cache, so the tests need no network.

Hard rule: emergencies, safety checks, medicines, reminders, confirmations, calls and fallbacks ALWAYS use Arjun's
own voice, so a cloned voice can never be the one telling an elder something urgent or asking them to act.
"""

import base64
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx

ENABLED = os.environ.get("ARJUN_CLONED_VOICE", "1").strip() != "0"
# How the cloned voice is fetched from Gnani: "rest" (default: one complete WAV, heard clean on the laptop) or "sse"
# (streamed chunks). SSE produced loud noise on the laptop (2026-11-08 21:41) and did not start sooner (~3.3 s either
# way), so it is opt-in until the chunk format is confirmed with Gnani.
METHOD = os.environ.get("ARJUN_CLONED_VOICE_METHOD", "rest").strip().lower()
# Languages the cloned voice may speak, e.g. "hi,en" (prefix of the detected code). Empty = every language. Gnani's
# voice-clone API takes no language field, so Marathi text can come out Hindi-sounding; the family can keep Marathi
# in Arjun's own Timbre voice by leaving "mr" out.
LANGUAGES = tuple(x.strip().lower() for x in os.environ.get("ARJUN_CLONED_VOICE_LANGUAGES", "").split(",") if x.strip())
CACHE_S = 60.0
_CHAT_INTENTS = ("chat", "companion", "story", "smalltalk", "greeting", "memory")
_NEVER = ("emergency", "safety", "medicine", "reminder", "distress", "call", "confirm", "money", "appointment")


@dataclass(frozen=True)
class ClonedVoice:
    voice_id: int
    name: str
    embedding: str
    shape: list[int]
    dtype: str

    def speaker_embedding(self) -> dict[str, Any]:
        return {"embedding": self.embedding, "shape": self.shape, "dtype": self.dtype}


def allowed(reply: Any) -> bool:
    """True only for plain companion talk. Anything urgent, actionable or uncertain stays in Arjun's voice."""
    mode = (getattr(reply, "mode", "") or "").lower()
    screen = (getattr(reply, "screen", "") or "reply").lower()
    intent = (getattr(reply, "intent", "") or "").lower()
    action = getattr(reply, "action", None) or {}
    if mode in ("safety", "fallback", "care") or screen not in ("reply", "story"):
        return False
    if getattr(reply, "awaiting_confirmation", False):
        return False
    if action.get("type") not in (None, "", "none"):
        return False
    if any(word in intent for word in _NEVER):
        return False
    return any(intent.startswith(word) for word in _CHAT_INTENTS) or mode in ("companion", "story")


def language_allowed(detected: str | None, languages: tuple[str, ...] | None = None) -> bool:
    """May the cloned voice speak a reply in this detected language? Unknown language counts as allowed only when no
    list is set (so a configured list never lets an unidentified language through)."""
    langs = LANGUAGES if languages is None else languages
    if not langs:
        return True
    code = (detected or "").lower()
    return bool(code) and any(code.startswith(lang) for lang in langs)


class SseError(Exception):
    """Gnani reported an error inside the SSE stream."""


class SseParser:
    """Incremental reader for Gnani TTS SSE (same rules as the plugin's reader): skip keep-alives / metadata,
    accumulate JSON that spans lines, emit each audio chunk once, stop at is_final, raise on an error payload."""

    def __init__(self) -> None:
        self.buf = ""
        self.done = False

    def feed(self, raw: str) -> list[bytes]:
        out: list[bytes] = []
        for piece in raw.splitlines() or [raw]:
            line = piece.strip()
            if self.done or not line or line.startswith((":", "event:", "id:", "retry:")):
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
                if not line:
                    continue
            self.buf += line
            try:
                payload = json.loads(self.buf)
            except json.JSONDecodeError:
                continue
            self.buf = ""
            if payload.get("status") == "error" or "error" in payload:
                raise SseError(str(payload.get("message") or payload.get("error") or "error")[:200])
            if payload.get("status") == "streaming_started":
                continue
            if payload.get("audio"):
                out.append(base64.b64decode(payload["audio"]))
            if payload.get("is_final"):
                self.done = True
        return out


def cloned_payload(base: dict[str, Any], voice: ClonedVoice) -> dict[str, Any]:
    """Turn a Timbre REST payload into a Voice Cloned TTS one: same text + audio_config, the speaker embedding,
    model vachana-vc-v1, and no preset voice/language (the cloned voice replaces them)."""
    payload = {k: v for k, v in base.items() if k not in ("voice", "language")}
    payload["model"] = "vachana-vc-v1"
    payload["speaker_embedding"] = voice.speaker_embedding()
    return payload


class VoiceSource:
    """The elder's active cloned voice from core-api, re-checked every CACHE_S so a delete/deactivate on the
    dashboard takes effect within a minute. Never raises: any problem means 'speak as Arjun'."""

    def __init__(self, user_id: int, fetch: Callable[[int], dict[str, Any] | None] | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.user_id, self._fetch, self._clock = user_id, fetch or fetch_active, clock
        self._value: ClonedVoice | None = None
        self._at = -1e9

    def get(self) -> ClonedVoice | None:
        if not ENABLED:
            return None
        if self._clock() - self._at < CACHE_S:
            return self._value
        self._at = self._clock()
        try:
            data = self._fetch(self.user_id)
        except Exception:  # noqa: BLE001 - a missing voice must never break a turn
            data = None
        self._value = (
            ClonedVoice(int(data["voice_id"]), str(data["name"]), str(data["embedding"]),
                        list(data.get("shape") or []), str(data.get("dtype") or ""))
            if data and data.get("embedding") else None
        )
        return self._value

    def forget(self) -> None:
        """After a failed cloned synthesis: speak as Arjun until the next re-check."""
        self._value, self._at = None, self._clock()


def _core() -> tuple[str, dict[str, str]]:
    base = os.environ.get("CORE_API_URL", "http://127.0.0.1:8000").rstrip("/")
    headers = {"X-API-Key": os.environ["CORE_API_KEY"]} if os.environ.get("CORE_API_KEY") else {}
    return base, headers


def fetch_active(user_id: int) -> dict[str, Any] | None:
    base, headers = _core()
    res = httpx.get(f"{base}/internal/users/{user_id}/cloned-voice", headers=headers, timeout=2.0)
    if res.status_code == 404:
        return None
    res.raise_for_status()
    return res.json()


def report_used(user_id: int, voice_id: int) -> None:
    """Audit trail for the family: best effort, never blocks or breaks speech."""
    try:
        base, headers = _core()
        httpx.post(f"{base}/internal/users/{user_id}/cloned-voice/{voice_id}/used", headers=headers, timeout=2.0)
    except httpx.HTTPError:
        pass
