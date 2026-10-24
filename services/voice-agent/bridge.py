"""HTTP bridge from the voice worker to reasoning. No business logic lives in the voice agent.

Rule: a failed or slow reasoning call must never leave Aaji in silence. `reply_or_fallback`
always returns something speakable; the error is logged, never spoken in detail.
"""

import logging
import os
import time
from dataclasses import dataclass

import httpx

REASONING_URL = os.environ.get("REASONING_URL", "http://127.0.0.1:8001")
# A voice user cannot wait long: fail fast and speak the fallback instead.
REASONING_TIMEOUT_S = float(os.environ.get("REASONING_TIMEOUT_S", "5"))

log = logging.getLogger("arjun.bridge")

# Fixed fallback lines, by STT language prefix. Spoken only when reasoning fails.
FALLBACK_REPLY = {
    "mr": "माफ करा, मला नीट ऐकू आलं नाही. पुन्हा सांगाल का?",
    "hi": "माफ़ कीजिए, मैं ठीक से समझ नहीं पाया. क्या आप फिर से बताएँगे?",
    "en": "Sorry, I didn't catch that. Could you say it again?",
}

_client: httpx.Client | None = None


def _shared_client() -> httpx.Client:
    """One pooled client for the worker process (thread-safe for concurrent requests)."""
    global _client
    if _client is None:
        _client = httpx.Client(timeout=REASONING_TIMEOUT_S)
    return _client


@dataclass
class BridgeReply:
    text: str
    mode: str
    awaiting_confirmation: bool
    round_trip_ms: float


def ask_reasoning(user_id: int, transcript: str, http: httpx.Client | None = None) -> BridgeReply:
    """Call reasoning /turn. Raises on HTTP or network errors (see reply_or_fallback)."""
    client = http or _shared_client()
    t0 = time.perf_counter()
    r = client.post(f"{REASONING_URL}/turn", json={"user_id": user_id, "text": transcript})
    r.raise_for_status()
    data = r.json()
    return BridgeReply(
        text=data["reply"],
        mode=data["mode"],
        awaiting_confirmation=data["awaiting_confirmation"],
        round_trip_ms=(time.perf_counter() - t0) * 1000,
    )


def fallback_text(language: str) -> str:
    return FALLBACK_REPLY.get((language or "mr").split("-")[0].lower(), FALLBACK_REPLY["mr"])


def reply_or_fallback(
    user_id: int, transcript: str, language: str, http: httpx.Client | None = None
) -> BridgeReply:
    """Like ask_reasoning, but any failure becomes a spoken fallback (mode="fallback")."""
    t0 = time.perf_counter()
    try:
        return ask_reasoning(user_id, transcript, http)
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.error("reasoning call failed (%s): %s", type(exc).__name__, exc)
        return BridgeReply(
            text=fallback_text(language),
            mode="fallback",
            awaiting_confirmation=False,
            round_trip_ms=(time.perf_counter() - t0) * 1000,
        )


def should_speak(reply: BridgeReply, stale: bool) -> bool:
    """Speak this reply? An outdated one is dropped: the user has already said something newer, and
    answering the old sentence is how Arjun seemed to reply to the wrong thing (2026-10-24).

    The one exception is a reply that asks for a yes/no: reasoning has already stored a pending action,
    so the user must hear what they would be agreeing to, or a later spoken "yes" would confirm blind.
    """
    return (not stale) or reply.awaiting_confirmation


def endpointing_delay(mode: str) -> float:
    """Seconds of silence before end-of-turn. Companion tolerates longer pauses than care mode.

    PLACEHOLDER values - must be measured on elderly-speaker audio (CLAUDE.md: measure, don't guess).
    """
    return 1.2 if mode == "companion" else 1.0
