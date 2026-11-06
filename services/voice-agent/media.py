"""Media mode (pure): while a video plays, the microphone also hears the video, so most transcripts are NOT her.

A transcript is sent to reasoning only when it starts with the wake word ("अर्जुन" / "arjun"), is a bare
control phrase (stop / next / volume), or contains an emergency / distress phrase. Everything else is
dropped and logged as "ignored_media" without the words. `should_send` is local and synchronous: a video's
own audio must never reach reasoning, and safety must never depend on a service being up.
"""

import re
import time

from safety_words import is_safety_phrase

ATTR_MEDIA = "arjun.media"  # set by the ELDER PAGE on its own participant: "playing" | "stopped"
MEDIA_KINDS = frozenset({"youtube_video", "youtube_playlist", "youtube_channel_live", "youtube_live"})
WAKE_WORDS = ("अर्जुन", "अर्जून", "अर्जन", "अर्जुना", "arjun", "arjoon", "arjuna")
CONTROL_PHRASES = (
    "थांबव", "थांबवा", "थांब", "थांबा", "बंद कर", "बंद करा", "बंद कर ना", "बंद करो", "बंद", "पॉज",
    "रोक", "रोक दो", "पॉज़", "अगला", "अगली", "पिछला", "पीछे", "आवाज़ बढ़ाओ", "आवाज बढ़ाओ",
    "आवाज़ कम करो", "आवाज कम करो", "फिर से", "चलाओ",
    "पुढचं", "पुढे", "मागचं", "मागे", "आवाज कमी कर", "आवाज वाढव",
    "आवाज कमी", "आवाज वाढवा", "परत", "stop",
    "pause", "next", "play", "resume",
)
MAX_CONTROL_WORDS = 4

_PUNCT = re.compile(r"[\s,.!?।;:\"“”‘’()\[\]{}\-–—]+")
_CONTROL = frozenset(" ".join(p.split()) for p in CONTROL_PHRASES)


def _words(text: str) -> list[str]:
    return [w for w in _PUNCT.split(text.strip().lower()) if w]


def normalize(text: str) -> str:
    """Lower-case, punctuation dropped, whitespace collapsed; Devanagari kept whole (matras stay in the word)."""
    return " ".join(_words(text))


def starts_with_wake_word(text: str) -> bool:
    """"अर्जुन, थांबव" / "Arjun stop": the first word is his name."""
    words = _words(text)
    return bool(words) and words[0] in WAKE_WORDS


def strip_wake_word(text: str) -> str:
    """Drop a leading "अर्जुन" / "arjun" and its punctuation; anything else is returned unchanged."""
    words = _words(text)
    if words and words[0] in WAKE_WORDS:
        return " ".join(words[1:])
    return text.strip()


def is_bare_control(text: str) -> bool:
    """A short control phrase (after a leading wake word), never a line of a song.

    STT adds particles ("बंद कर ना", "थांब रे") and suffixes ("बंद करा"), so we match when any
    known control phrase is contained in the normalised text, not only on an exact equality."""
    norm = normalize(strip_wake_word(text))
    if not norm:
        return False
    if norm in _CONTROL:
        return True
    words = norm.split()
    if len(words) > MAX_CONTROL_WORDS:
        return False
    for phrase in _CONTROL:
        if phrase in norm:
            return True
    return False


def should_send(transcript: str, playing: bool) -> bool:
    """Send this transcript to reasoning? Not playing: always. Playing: only her, a control, or a safety phrase."""
    if not playing:
        return True
    if starts_with_wake_word(transcript):
        return True
    if is_bare_control(transcript):
        return True
    return is_safety_phrase(transcript)


class MediaState:
    """Whether a video is playing, from the page's own attribute and from the actions we publish."""

    def __init__(self, playing: bool = False, clock=time.monotonic) -> None:
        self.playing = playing
        self._clock = clock
        self.last_heartbeat = clock() if playing else None

    def on_action(self, action: dict | None) -> None:  # type: ignore[type-arg]
        """Only a page player report may turn media mode on; an explicit stop turns it off immediately."""
        if not action:
            return
        if action.get("type") == "control" and action.get("kind") == "stop":
            self.playing = False

    def on_page_state(self, value: str | None) -> None:
        """The elder page reports what its player is doing ("arjun.media")."""
        if value == "playing":
            self.playing = True
            self.last_heartbeat = self._clock()
        elif value in ("stopped", "", None):
            self.playing = False
            self.last_heartbeat = None

    def heartbeat_expired(self, timeout_s: float = 30.0) -> bool:
        return self.playing and self.last_heartbeat is not None and self._clock() - self.last_heartbeat >= timeout_s

    def reset(self) -> None:
        """The page left the room: nothing is playing for us any more."""
        self.playing = False
        self.last_heartbeat = None
