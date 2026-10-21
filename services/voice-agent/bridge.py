"""HTTP bridge from the voice worker to reasoning. No business logic lives in the voice agent."""

import os
import time
from dataclasses import dataclass

import httpx

REASONING_URL = os.environ.get("REASONING_URL", "http://reasoning:8001")


@dataclass
class BridgeReply:
    text: str
    mode: str
    awaiting_confirmation: bool
    round_trip_ms: float


def ask_reasoning(user_id: int, transcript: str, http: httpx.Client | None = None) -> BridgeReply:
    client = http or httpx.Client(timeout=15.0)
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


def endpointing_delay(mode: str) -> float:
    """Seconds of silence before end-of-turn. Companion tolerates longer pauses than care mode.

    PLACEHOLDER values - must be measured on elderly-speaker audio (CLAUDE.md: measure, don't guess).
    """
    return 1.2 if mode == "companion" else 0.7
