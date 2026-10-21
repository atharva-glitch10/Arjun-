"""Text normalisation + keyword matching shared by the rule-based parser and distress check."""

import re

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_PUNCT = re.compile(r"[,.?!।;\"“”‘’()\[\]{}]+")


def normalize(text: str) -> str:
    t = text.lower().translate(_DEVANAGARI_DIGITS)
    t = _PUNCT.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def has_any(norm: str, phrases: tuple[str, ...] | list[str]) -> bool:
    """Whole-token / whole-phrase containment on normalised text."""
    padded = f" {norm} "
    return any(f" {p} " in padded for p in phrases)


def tokens(norm: str) -> list[str]:
    return norm.split(" ") if norm else []


def has_devanagari(text: str) -> bool:
    return any("ऀ" <= ch <= "ॿ" for ch in text)


_MR_MARKERS = (
    "आहे", "नाही", "मला", "तुम्ही", "काय", "उद्या", "करा", "सांगा", "aahe", "ahe", "mala",
    "nahi", "tumhi", "kay", "udya", "sakali", "vajta", "jaycha", "karaycha", "mazya", "hoy",
)
_HI_MARKERS = (
    "है", "नहीं", "मुझे", "क्या", "कल", "हूँ", "हैं", "करो", "hai", "nahin", "mujhe", "kya",
    "kal", "hoon", "karo", "baje", "haan", "subah", "shaam",
)
_EN_MARKERS = ("the", "is", "to", "what", "my", "remind", "me", "today", "tomorrow", "yes", "no")


def detect_language(text: str, default: str) -> str:
    norm = normalize(text)
    toks = set(tokens(norm))
    mr = len(toks & set(_MR_MARKERS))
    hi = len(toks & set(_HI_MARKERS))
    en = len(toks & set(_EN_MARKERS))
    best = max(mr, hi, en)
    if best == 0:
        return default
    if mr == best and mr >= hi:
        return "mr"
    if hi == best:
        return "hi"
    return "en"
