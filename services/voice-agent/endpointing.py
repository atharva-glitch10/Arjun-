"""Mode-aware endpointing and the "half a sentence" hold (task D, 2026-10-31).

Elderly speakers pause in the middle of a sentence ("... डोकं दुखतं आहे माझं थोडं आणि ..."). One fixed delay is wrong in
both directions: a reminder command wants a quick answer, a story wants patience. So the delay follows the mode of
the LAST reply (the mode of the conversation she is in):

  care       (reminders, schedule, medicines, safety, fallback)  min 0.8 s, max 2.5 s
  companion  (stories, chat)                                      min 1.6 s, max 4.0 s

Trade-off, stated plainly: every companion turn answers about 0.8 s later than with the care timing (1.6 s of silence
instead of 0.8 s) in exchange for far fewer sentences cut in half. The numbers are PLACEHOLDERS until they are tuned
on real elderly speech (CLAUDE.md open question 7); each is an env variable.

Conjunction hold: a final transcript ending in "आणि / पण / म्हणजे / की" is almost never finished. The session waits for
more speech for the rest of the max delay (max - min: the silence already waited counts) before calling reasoning. If she
starts talking again, the two parts are joined and answered once. Pure and tested; nothing here sleeps by itself.
"""

import os
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

_CONJUNCTIONS = frozenset({
    "आणि", "अन", "पण", "म्हणजे", "की", "आणखी", "परंतु",  # Marathi
    "और", "लेकिन", "कि", "मगर",  # Hindi
    "ani", "pan", "mhanje", "ki", "aani", "aur", "lekin", "and", "but",
})
_TRAILING = re.compile(r"[\s,.;:!?।…\-\"'“”‘’]+$")


def ends_with_conjunction(text: str) -> bool:
    """True when the last word is one that begins another clause, so the sentence is not finished."""
    cleaned = _TRAILING.sub("", text or "")
    if not cleaned:
        return False
    return cleaned.split()[-1].lower() in _CONJUNCTIONS


@dataclass(frozen=True)
class EndpointingSettings:
    care_min: float = 0.8
    care_max: float = 2.5
    companion_min: float = 1.6
    companion_max: float = 4.0


def settings_from_env(env: Mapping[str, str] | None = None) -> EndpointingSettings:
    e = os.environ if env is None else env

    def num(name: str, default: float) -> float:
        try:
            v = float((e.get(name) or "").strip())
        except ValueError:
            return default
        return v if v > 0 else default

    d = EndpointingSettings()
    care_min = num("ARJUN_MIN_ENDPOINTING_S", d.care_min)
    companion_min = num("ARJUN_COMPANION_MIN_ENDPOINTING_S", d.companion_min)
    return EndpointingSettings(
        care_min=care_min,
        care_max=max(num("ARJUN_CARE_MAX_ENDPOINTING_S", d.care_max), care_min),
        companion_min=companion_min,
        companion_max=max(num("ARJUN_MAX_ENDPOINTING_S", d.companion_max), companion_min),
    )


class EndpointingPolicy:
    """The delay pair in force right now. Starts in care timing; each reply's mode sets the next turn's."""

    def __init__(self, settings: EndpointingSettings | None = None) -> None:
        self.settings = settings or settings_from_env()
        self.mode = "care"

    def set_mode(self, reply_mode: str) -> None:
        self.mode = "companion" if reply_mode == "companion" else "care"  # safety / fallback / unknown: quick

    def options(self) -> dict[str, float]:
        s = self.settings
        if self.mode == "companion":
            return {"min_delay": s.companion_min, "max_delay": s.companion_max}
        return {"min_delay": s.care_min, "max_delay": s.care_max}


class ConjunctionHold:
    """Decides, for each completed spoken turn, whether to answer now or wait for the rest of the sentence."""

    def __init__(self, policy: EndpointingPolicy, wait_for_speech: Callable[[float], Awaitable[bool]]) -> None:
        self.policy = policy
        self.wait_for_speech = wait_for_speech  # (timeout_s) -> did she start speaking again within it?
        self.held = ""

    async def settle(self, transcript: str, allow_hold: bool = True) -> str | None:
        """The text to answer now, or None = held (she is still talking; the next turn continues it).
        "" = nothing to answer. A tap/text turn (allow_hold=False) drops any held part and is answered as is."""
        if not allow_hold:
            self.held = ""
            return transcript
        spoken = transcript.strip()
        if not spoken:  # noise after a held part: answer what we kept rather than lose it
            text, self.held = self.held, ""
            return text
        text = f"{self.held} {spoken}".strip() if self.held else spoken
        if ends_with_conjunction(text):
            opts = self.policy.options()
            rest = max(0.0, opts["max_delay"] - opts["min_delay"])
            if rest > 0 and await self.wait_for_speech(rest):
                self.held = text
                return None
        self.held = ""
        return text
