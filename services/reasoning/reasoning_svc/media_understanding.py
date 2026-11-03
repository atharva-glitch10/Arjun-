"""What a media request is ABOUT: one strict-JSON call to the LLM, with the rules as the fallback.

The old parser could only see "YouTube" + "play": it opened a search page and asked a generic question.
This module answers the two things the screen needs - the kind (news / recipe / music / devotional /
exercise / video / unknown) and whether she named a particular singer, dish or programme - so reasoning
can play a named item directly or offer three real choices.

Rules still decide safety, medicines and reminders before this is ever called (see turn._intent), and a
slow or broken LLM (3 s) simply leaves the rule answer in place. The LLM never produces a URL, a video id
or a reply: only these three fields, and every field is validated here.

The lexicon in appcmd is UNVERIFIED (no native-speaker review), like the safety lexicons.
"""

import logging
from dataclasses import dataclass

from .appcmd import media_kind, media_specific, media_topic
from .textutil import normalize

log = logging.getLogger("reasoning.media")

KINDS = frozenset({"news", "recipe", "music", "devotional", "exercise", "video", "unknown"})
_CACHE_CAP = 256


@dataclass(frozen=True)
class MediaRequest:
    kind: str
    topic: str
    specific: bool
    source: str  # "rules" | "llm"


_cache: dict[str, MediaRequest] = {}


def clear_cache() -> None:
    _cache.clear()


def rules_media_request(text: str) -> MediaRequest:
    """The current rule answer: the fallback when there is no LLM, it times out, or its JSON is invalid."""
    kind = media_kind(text)
    topic = media_topic(text)
    return MediaRequest(kind, topic, media_specific(text, kind, topic), "rules")


def _valid(data: object) -> dict[str, object] | None:
    if not isinstance(data, dict):
        return None
    kind = data.get("kind")
    topic = data.get("topic")
    specific = data.get("specific")
    if kind not in KINDS:
        return None
    if not isinstance(topic, str):
        return None
    return {"kind": kind, "topic": topic.strip()[:100], "specific": bool(specific)}


def _merge(llm: dict[str, object], rules: MediaRequest) -> MediaRequest:
    """The LLM's reading, with the rules filling a gap: an "unknown" kind never erases a rule that saw news or a
    recipe, and a named item needs words to search for."""
    kind = str(llm["kind"])
    if kind == "unknown" and rules.kind != "unknown":
        kind = rules.kind
    topic = str(llm["topic"]) or rules.topic
    specific = bool(llm["specific"]) and bool(topic)
    return MediaRequest(kind, topic, specific, "llm")


def understand_media(llm: object, text: str, *, timeout: float = 3.0) -> MediaRequest:
    """Understand one utterance, cached per normalised text.

    `llm` may be None or a test double without `media_understanding`; then the rules answer is used and
    nothing is called. A failed call is not cached as if it were a model answer: it is retried next time.
    """
    key = normalize(text)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    rules = rules_media_request(text)
    result = rules
    if llm is not None and hasattr(llm, "media_understanding"):
        try:
            data = llm.media_understanding(text, timeout=timeout)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001 - a slow/broken provider must never break the turn
            log.info("media understanding failed: %s", type(exc).__name__)
            data = None
        valid = _valid(data)
        if valid is not None:
            result = _merge(valid, rules)
            if len(_cache) >= _CACHE_CAP:
                _cache.clear()
            _cache[key] = result
    return result
