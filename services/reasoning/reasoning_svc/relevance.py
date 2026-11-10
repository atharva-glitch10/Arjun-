"""Relevance guard helpers (2026-11-10): is the reply ABOUT what she just said / the running conversation? Rules first (cheap word
overlap against her sentence, the topic, the people named and the open question); a small LLM yes/no only when the overlap is low
(turn.py). The fixed clarifying question quotes HER words, never a generic line. Translations below are UNVERIFIED by a native
speaker (like the other lexicons)."""

from __future__ import annotations

import re

from .convstate import _FUNCTION, SHORT_ANSWERS, is_short_answer
from .memory import _stems, norm

PASS_SCORE = 0.2  # share of her content stems (plus topic / entities / open question) that the reply picks up again
_GENERIC = re.compile(
    r"^\s*(?:ठीक आहे|बरं|बरं का|हो का|अच्छा|सांगा ना|सांगा|मी ऐकतोय|मी ऐकत आहे|ऐकतोय|ठीक है|बताइए|मैं सुन रहा हूँ|मैं सुन रहा हूं|"
    r"okay|ok|i'?m listening|go on|tell me more|i see|alright|sure)[\s.!?।…]*$", re.IGNORECASE,
)
# What a reply that wanders off usually does: opens a new subject. Not a rule by itself, only a reason to look closer.
_CLARIFY = {
    "mr": "“{q}” म्हणजे नक्की काय, थोडं सांगाल का?",
    "hi": "“{q}” मतलब ठीक से क्या, ज़रा बताइए?",
    "en": "“{q}” - what exactly do you mean, could you tell me a little more?",
    "bn": "“{q}” বলতে ঠিক কী বোঝাচ্ছেন, একটু বলবেন?",
    "gu": "“{q}” એટલે બરાબર શું, થોડું કહેશો?",
    "kn": "“{q}” ಎಂದರೆ ನಿಖರವಾಗಿ ಏನು, ಸ್ವಲ್ಪ ಹೇಳುವಿರಾ?",
    "ml": "“{q}” എന്നാൽ കൃത്യമായി എന്താണ്, ഒന്ന് പറയാമോ?",
    "pa": "“{q}” ਦਾ ਮਤਲਬ ਕੀ ਹੈ, ਥੋੜ੍ਹਾ ਦੱਸੋਗੇ?",
    "ta": "“{q}” என்றால் சரியாக என்ன, கொஞ்சம் சொல்வீர்களா?",
    "te": "“{q}” అంటే సరిగ్గా ఏమిటి, కొంచెం చెప్తారా?",
}
_WORD = re.compile(r"[\wऀ-ॿঀ-෿]+")


def is_generic(reply: str) -> bool:
    """A filler line that answers nothing ("ठीक आहे.", "सांगा ना", "okay")."""
    return bool(_GENERIC.match(reply or ""))


def content_words(text: str) -> list[str]:
    return [w for w in _WORD.findall(text or "") if w not in _FUNCTION and w not in SHORT_ANSWERS and len(w) > 1]


def score(text: str, reply: str, *, topic: str = "", entities: list[str] | None = None, pending: str = "") -> float:
    """0..1: how much of what she said (and of the running topic) the reply picks up. A short answer ("हो", "तेच") is scored against
    the question it answers and the topic instead, because it has no content words of its own."""
    reply_stems = _stems(reply)
    if not reply_stems:
        return 0.0
    anchors: list[set[str]] = []
    if not is_short_answer(text):
        anchors.append(_stems(" ".join(content_words(text))))
    for extra in (topic, " ".join(entities or []), pending):
        if extra:
            anchors.append(_stems(extra))
    best = 0.0
    for a in anchors:
        if a:
            best = max(best, len(a & reply_stems) / len(a))
    return round(min(1.0, best), 3)


def clarify(text: str, lang: str) -> str:
    """A short question that quotes her own words (at most 6 content words), in her language."""
    words = content_words(text)[:6] or norm(text).split()[:6]
    quote = " ".join(words).strip() or text.strip()[:40]
    return _CLARIFY.get(lang, _CLARIFY["en"]).format(q=quote)
