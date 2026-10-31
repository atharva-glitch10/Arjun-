"""Conversation tracker: turns one conversation into one line for the family (seriousness, mood, summary).

    turn ──record()──▶ in-memory buffer (this conversation only)
    3 min of silence ──flush_idle() (called by the scheduler every tick)──▶ core-api /wellbeing ──▶ family feed

What the family gets depends on the elder's consent setting (`consent_distress_alert`, shown on the dashboard as
"share how she is doing"):
  consent ON : mood + a short summary (by the LLM when configured, else built from the intents) + seriousness.
  consent OFF: only what she did ("set 2 reminders, chatted") and seriousness for help requests / emergencies.
              Feelings (lonely, upset) are never shown without consent.
The seriousness is never LOWER than the rules floor (an emergency stays an emergency whatever the LLM says).
The buffer lives in memory only, is capped at 40 turns and is dropped after the summary is sent. No transcript
is ever stored in core-api.
"""

from __future__ import annotations

import logging
import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

import httpx

from . import config
from .clock import local_now
from .core_client import CoreClient, CoreError

log = logging.getLogger("reasoning.wellbeing")

RANK = {"normal": 0, "watch": 1, "urgent": 2, "emergency": 3}

# intent -> (seriousness floor, needs consent to show?)
FLOOR: dict[str, tuple[str, bool]] = {
    "EMERGENCY": ("emergency", False),
    "REQUEST_CAREGIVER": ("urgent", False),
    "DISTRESS": ("urgent", True),
    "LONELY": ("watch", True),
    "SYMPTOM": ("watch", True),
    "MEDICAL_QUESTION": ("watch", False),
}
MOOD_BY_INTENT = {"EMERGENCY": "unwell", "DISTRESS": "distressed", "LONELY": "lonely", "SYMPTOM": "unwell"}

# what she did, in plain words for the family (rules summary; no words of hers)
DID = {
    "CREATE_REMINDER": "set a reminder",
    "COMPLETE_REMINDER": "marked a reminder done",
    "MED_TAKEN": "said she took a medicine",
    "MED_SNOOZE": "put off a medicine",
    "LIST_TODAY": "asked about her day",
    "TIME_QUERY": "asked the time",
    "NEXT_UP": "asked what is next",
    "GET_APPOINTMENT": "asked about an appointment",
    "CALL_FAMILY_REMINDER": "talked about calling family",
    "REQUEST_CAREGIVER": "asked for help",
    "SHARE_STORY_WITH_FAMILY": "shared a story with the family",
    "CHAT": "chatted",
    "MEDICAL_QUESTION": "asked about a medicine (Arjun did not answer it)",
    "EMERGENCY": "reported a physical emergency",
    "DISTRESS": "sounded very upset",
    "LONELY": "said she feels lonely",
    "SYMPTOM": "mentioned a health complaint",
}


@dataclass
class Conversation:
    started: datetime
    last: datetime
    turns: list[tuple[str, str]] = field(default_factory=list)  # (role, text); memory only
    intents: list[str] = field(default_factory=list)


def _max(*levels: str) -> str:
    return max(levels, key=lambda x: RANK.get(x, 0), default="normal")


class Tracker:
    def __init__(
        self,
        core: CoreClient,
        llm: Any | None = None,
        clock: Callable[[], datetime] = local_now,
        idle_s: float = config.CONVERSATION_IDLE_S,
    ) -> None:
        self.core, self.llm, self.clock = core, llm, clock
        self.idle = timedelta(seconds=idle_s)
        self._convs: dict[int, Conversation] = {}
        self._lock = threading.Lock()

    def record(self, uid: int, said: str, reply: str, intent: str) -> None:
        """One finished turn. Never raises (it runs after the reply was sent)."""
        now = self.clock()
        finished: Conversation | None = None
        with self._lock:
            conv = self._convs.get(uid)
            if conv is not None and now - conv.last > self.idle:
                finished = self._convs.pop(uid)
                conv = None
            if conv is None:
                conv = self._convs[uid] = Conversation(started=now, last=now)
            conv.last = now
            conv.turns += [("user", said), ("assistant", reply)]
            conv.turns = conv.turns[-40:]
            conv.intents.append(intent)
        if finished is not None:
            self._send(uid, finished)

    def flush_idle(self, now: datetime | None = None) -> int:
        """Send every conversation that has been quiet for `idle`. Returns how many were sent."""
        now = now or self.clock()
        with self._lock:
            done = [(uid, c) for uid, c in self._convs.items() if now - c.last > self.idle]
            for uid, _ in done:
                self._convs.pop(uid, None)
        for uid, conv in done:
            self._send(uid, conv)
        return len(done)

    def open_count(self) -> int:
        return len(self._convs)

    # ------------------------------------------------------------------
    def entry(self, conv: Conversation, consent: bool, language: str = "mr") -> dict[str, Any]:
        """The wellbeing row for one conversation (pure apart from the optional LLM call)."""
        floor = "normal"
        moods = []
        for i in conv.intents:
            level, sensitive = FLOOR.get(i, ("normal", False))
            if consent or not sensitive:
                floor = _max(floor, level)
            if i in MOOD_BY_INTENT and (consent or i == "EMERGENCY"):
                moods.append(MOOD_BY_INTENT[i])
        n = len(conv.intents)
        counts = Counter(i for i in conv.intents if i in DID and (consent or not FLOOR.get(i, ("", False))[1]))
        did = ", ".join(f"{DID[i]}{f' ({c}x)' if c > 1 else ''}" for i, c in counts.most_common(5))
        summary = f"Talked with Arjun ({n} turn{'s' if n != 1 else ''})" + (f": {did}." if did else ".")
        row: dict[str, Any] = {
            "kind": "conversation", "severity": floor, "mood": moods[-1] if moods else "not_assessed",
            "summary": summary[:400], "turns": n, "source": "rules", "started_at": conv.started.isoformat(),
        }
        if consent and self.llm is not None:
            try:
                got = self.llm.summarize_conversation(conv.turns, language)
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                log.warning("summary LLM failed: %s", type(exc).__name__)
                got = None
            if got:
                row.update(
                    summary=got["summary"] or row["summary"],
                    mood=got["mood"],
                    severity=_max(floor, got["severity"]),  # the LLM may raise the level, never lower it
                    source="llm",
                )
        return row

    def _send(self, uid: int, conv: Conversation) -> None:
        try:
            user = self.core.user(uid)
            row = self.entry(conv, bool(user.get("consent_distress_alert")), user.get("language", "mr"))
            self.core.wellbeing(uid, row)
        except (CoreError, httpx.HTTPError, KeyError) as exc:
            log.warning("could not send conversation summary for user %s: %s", uid, exc)
