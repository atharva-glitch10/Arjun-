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
    screen: str = "reply"  # reply | story | confirm | saved | safety (decided by reasoning)
    intent: str = ""
    speech: str = ""  # what to say, may carry Timbre v3 tags; empty = say `text`
    source: str = ""  # rules | llm: who wrote the answer (for the turn log)
    action: dict | None = None  # type: ignore[type-arg]  # what the elder screen opens / does: {type, kind, value, title}


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
        screen=data.get("screen", "reply"),
        intent=data.get("intent", ""),
        speech=data.get("speech", "") or "",
        source=data.get("source", "") or "",
        action=data.get("action") or None,
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


# Spoken (fixed text) when an idle session ends (only if ARJUN_IDLE_CLOSE_S > 0; hands-free never closes).
# It names the talk button of the elder screen exactly: "बोला".
CLOSING_REPLY = {
    "mr": "ठीक आहे. गरज लागली तर 'बोला' दाबा.",
    "hi": "ठीक है। ज़रूरत हो तो 'बोला' दबाइए।",
    "en": "Okay. If you need me, press 'बोला'.",
}


def closing_text(language: str) -> str:
    return CLOSING_REPLY.get((language or "mr").split("-")[0].lower(), CLOSING_REPLY["mr"])


# ---- T8: queued reminders / medicine prompts (the agent only knows reasoning, never core-api) ----------------
def claim_next_delivery(user_id: int, session: str, http: httpx.Client | None = None) -> dict | None:  # type: ignore[type-arg]
    """Claim + render the next waiting item for this session, or None (also when reasoning is down)."""
    client = http or _shared_client()
    try:
        r = client.post(f"{REASONING_URL}/delivery/next", json={"user_id": user_id, "session": session})
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("delivery lookup failed (%s): %s", type(exc).__name__, exc)
        return None


def mark_delivery_spoken(user_id: int, delivery_id: int, session: str, http: httpx.Client | None = None) -> None:
    """Report an item as spoken. Call ONLY after playback finished. Raises on failure so the caller can retry."""
    client = http or _shared_client()
    client.post(f"{REASONING_URL}/delivery/{delivery_id}/spoken", json={"user_id": user_id, "session": session}).raise_for_status()


def release_delivery(user_id: int, delivery_id: int, session: str, reason: str, http: httpx.Client | None = None) -> None:
    client = http or _shared_client()
    body = {"user_id": user_id, "session": session, "reason": reason}
    client.post(f"{REASONING_URL}/delivery/{delivery_id}/release", json=body).raise_for_status()


def session_busy(user_id: int, http: httpx.Client | None = None) -> dict | None:  # type: ignore[type-arg]
    """Pending yes/no, recent safety reply, queued items. None when it cannot be asked (never guess)."""
    client = http or _shared_client()
    try:
        r = client.get(f"{REASONING_URL}/session/{user_id}/busy")
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]
    except (httpx.HTTPError, ValueError):
        return None


def media_gate(user_id: int, text: str, http: httpx.Client | None = None) -> dict | None:  # type: ignore[type-arg]
    """While a video plays: is this transcript a safety phrase or a bare control phrase? None when it cannot be asked
    (the caller then passes the transcript on: safety is never ignored)."""
    client = http or _shared_client()
    try:
        r = client.post(f"{REASONING_URL}/media/gate", json={"user_id": user_id, "text": text})
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("media gate unavailable (%s)", type(exc).__name__)
        return None


def should_speak(reply: BridgeReply, stale: bool) -> bool:
    """Speak this reply? An outdated one is dropped: the user has already said something newer, and
    answering the old sentence is how Arjun seemed to reply to the wrong thing (2026-10-24).

    Only plain care and companion replies (and the spoken fallback) may be skipped. Never skipped:
    - mode "safety" (emergency / distress): 112, calling out for help, Elderline. Always spoken.
    - a reply that asks for a yes/no: reasoning has already stored a pending action. Skipping the reply
      would leave an action the user never heard, which a later "हो" would confirm blind. We speak the
      question instead of rejecting the action: the request is kept and the user hears what a "हो" does.
      This relies on reasoning flagging every pending action with awaiting_confirmation
      (tests/test_pending_is_announced.py).
    """
    return stale is False or reply.mode == "safety" or reply.awaiting_confirmation


def endpointing_delay(mode: str) -> float:
    """Seconds of silence before end-of-turn. Companion tolerates longer pauses than care mode.

    PLACEHOLDER values - must be measured on elderly-speaker audio (CLAUDE.md: measure, don't guess).
    """
    return 1.2 if mode == "companion" else 1.0
