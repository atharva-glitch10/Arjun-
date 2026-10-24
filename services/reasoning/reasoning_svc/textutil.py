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


def _collapse_k(tokens: list[str], k: int) -> list[str]:
    keys = [normalize(t) for t in tokens]
    out: list[str] = []
    i = 0
    while i < len(tokens):
        gram = keys[i : i + k]
        reps = 1
        if len(gram) == k and all(gram):
            while keys[i + reps * k : i + (reps + 1) * k] == gram:
                reps += 1
        if reps >= 3:  # three or more in a row is a recognizer artifact, not speech
            out.extend(tokens[i : i + k])
            i += reps * k
        else:
            out.append(tokens[i])
            i += 1
    return out


def collapse_repeats(text: str) -> str:
    """Collapse runaway repetition ("हो हो हो कर कर कर कर" -> "हो कर"): a word or a 2-3 word phrase repeated
    three or more times in a row. Two in a row ("नाही नाही") is normal speech and is left alone."""
    tokens = text.split()
    out = tokens
    for k in (1, 2, 3):
        out = _collapse_k(out, k)
    return " ".join(out) if out != tokens else text


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
