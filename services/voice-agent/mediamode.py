"""Media mode: while a video plays, the microphone also hears the video, so most transcripts are NOT the elder.

Rule (CLAUDE.md boundary 8 stays on top): a transcript is sent to reasoning only if it starts with the wake word
("अर्जुन" / "arjun"), or reasoning's rules say it is a bare control phrase (stop / next / volume) or a SAFETY phrase
(emergency or distress lexicon). Everything else is dropped and logged as "ignored_media" (the words are not kept).
If the check itself cannot be made (reasoning unreachable) the transcript is passed on, never ignored: a possible
"छातीत दुखतंय" must not be lost because a service was down.

The agent holds the lexicons nowhere: reasoning's `POST /media/gate` answers {"safety": bool, "control": bool}.
"""

import logging
import re
from collections.abc import Awaitable, Callable

try:
    from media import is_bare_control as _local_control
except Exception:  # pragma: no cover
    def _local_control(_t: str) -> bool:
        return False
from typing import Any

logger = logging.getLogger("arjun.media")

ATTR_MEDIA = "arjun.media"  # set by the ELDER PAGE on its own participant: "playing" | "stopped"
MEDIA_KINDS = frozenset({"youtube_video", "youtube_playlist", "youtube_channel_live"})
WAKE_WORDS = ("अर्जुन", "अर्जून", "अर्जन", "अर्जुना", "arjun", "arjoon", "arjuna")
_PUNCT = re.compile(r"[\s,.!?।;:\"“”‘’()\-]+")


def starts_with_wake_word(text: str) -> bool:
    """"अर्जुन, थांबव" / "Arjun stop": the first word is his name."""
    words = [w for w in _PUNCT.split(text.strip().lower()) if w]
    return bool(words) and words[0] in WAKE_WORDS


GateFn = Callable[[str], Awaitable[dict[str, Any] | None]]


class MediaMode:
    def __init__(self, gate: GateFn) -> None:
        self.gate = gate
        self.playing = False

    # ---- state ----------------------------------------------------------------------------------------------
    def on_action(self, action: dict[str, str] | None) -> None:
        """The agent just published an action: a video opening switches media mode on, a stop switches it off.
        (The page then confirms with its own `arjun.media` attribute.)"""
        if not action:
            return
        if action.get("type") == "open" and action.get("kind") in MEDIA_KINDS:
            self.playing = True
        elif action.get("type") == "control" and action.get("kind") == "stop":
            self.playing = False

    def on_page_state(self, value: str | None) -> None:
        """The elder page reports what its player is doing."""
        if value == "playing":
            self.playing = True
        elif value in ("stopped", "", None):
            self.playing = False

    def reset(self) -> None:
        self.playing = False  # the page left the room: nothing is playing for us any more

    # ---- the filter -----------------------------------------------------------------------------------------
    async def decide(self, transcript: str) -> tuple[str, str]:
        """("pass" | "ignore", reason). Safety is never ignored."""
        if not self.playing:
            return "pass", "not_playing"
        if starts_with_wake_word(transcript):
            return "pass", "wake_word"
        if _local_control(transcript):
            return "pass", "control"
        try:
            verdict = await self.gate(transcript)
        except Exception:  # noqa: BLE001 - when in doubt, pass it on
            logger.exception("media gate failed")
            verdict = None
        if verdict is None:
            return "pass", "gate_unavailable"
        if verdict.get("safety"):
            return "pass", "safety"
        if verdict.get("control"):
            return "pass", "control"
        return "ignore", "ignored_media"
