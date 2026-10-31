"""Reading a spoken BP reading: the numbers only, repeated back, never judged (CLAUDE.md boundary 7).

"माझा बीपी १३२ बाय ८६" -> (132, 86). The reply is a fixed template that repeats the same numbers in the
elder's script. No target, range, or word like good / bad / high / low / normal is added anywhere.
"""

import re

from .distress import fold

_DEVANAGARI = str.maketrans("०१२३४५६७८९", "0123456789")

# The BP word must be there, otherwise "132 by 86" is not a reading (never guess).
_BP_WORD = re.compile(r"(?<!\S)(?:बीपी|ब्लड\s*प्रेशर|रक्तदाब|bp|b\.p\.?|blood\s*pressure)(?!\S)", re.IGNORECASE)
_NUMBERS = re.compile(
    r"(?<!\d)(\d{2,3})\s*(?:बाय|वर|by|over|/|बटा)\s*(\d{2,3})(?!\d)",
    re.IGNORECASE,
)


def _ascii(text: str) -> str:
    return fold(text).translate(_DEVANAGARI)


def parse_bp(text: str) -> tuple[int, int] | None:
    """(systolic, diastolic) when she clearly said a BP reading, else None. Never guesses."""
    plain = _ascii(text).lower()
    if not _BP_WORD.search(plain):
        return None
    match = _NUMBERS.search(plain)
    if match is None:
        return None
    systolic, diastolic = int(match.group(1)), int(match.group(2))
    if not (40 <= systolic <= 300 and 20 <= diastolic <= 200 and systolic > diastolic):
        return None
    return systolic, diastolic


def _devanagari(number: int) -> str:
    return str(number).translate(str.maketrans("0123456789", "०१२३४५६७८९"))


def format_bp(systolic: int, diastolic: int, lang: str) -> str:
    """The same two numbers in the script the elder is speaking."""
    if lang in ("mr", "hi"):
        return f"{_devanagari(systolic)} बाय {_devanagari(diastolic)}"
    return f"{systolic} over {diastolic}"
