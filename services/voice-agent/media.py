"""Media mode (pure): while a video plays, the microphone also hears the video, so most transcripts are NOT her.

A transcript is sent to reasoning only when it starts with the wake word ("अर्जुन" / "arjun"), is a bare
control phrase (stop / next / volume), or contains an emergency / distress phrase. Everything else is
dropped and logged as "ignored_media" without the words. `should_send` is local and synchronous: a video's
own audio must never reach reasoning, and safety must never depend on a service being up.
"""

import re

from safety_words import is_safety_phrase

ATTR_MEDIA = "arjun.media"  # set by the ELDER PAGE on its own participant: "playing" | "stopped"
MEDIA_KINDS = frozenset({"youtube_video", "youtube_playlist", "youtube_channel_live", "youtube_live"})
WAKE_WORDS = ("अर्जुन", "अर्जून", "अर्जन", "अर्जुना", "arjun", "arjoon", "arjuna")
CONTROL_PHRASES = (
    "थांबव", "थांबवा", "बंद कर", "बंद करा", "पॉज", "पुढचं",
    "आवाज कमी कर", "आवाज वाढव", "stop", "pause", "next",
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
    """Exactly one of the short control phrases (after a leading wake word), never a line of a song."""
    norm = normalize(strip_wake_word(text))
    return bool(norm) and len(norm.split()) <= MAX_CONTROL_WORDS and norm in _CONTROL


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

    def __init__(self, playing: bool = False) -> None:
        self.playing = playing

    def on_action(self, action: dict | None) -> None:  # type: ignore[type-arg]
        """Called right after an action is published: a YouTube open starts media mode, a stop ends it."""
        if not action:
            return
        kind = str(action.get("kind", ""))
        if action.get("type") == "open" and (kind in MEDIA_KINDS or kind.startswith("youtube")):
            self.playing = True
        elif action.get("type") == "control" and kind == "stop":
            self.playing = False

    def on_page_state(self, value: str | None) -> None:
        """The elder page reports what its player is doing ("arjun.media")."""
        if value == "playing":
            self.playing = True
        elif value in ("stopped", "", None):
            self.playing = False

    def reset(self) -> None:
        """The page left the room: nothing is playing for us any more."""
        self.playing = False
