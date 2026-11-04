"""Generate services/voice-agent/safety_words.py from services/reasoning/reasoning_svc/distress.py.

distress.py is the ONE source of the safety lexicon. The voice agent keeps a local, import-free copy so media
mode can protect the elder when reasoning is down, but that copy is now GENERATED, never hand-edited.

    python scripts/gen_safety_words.py          # rewrite safety_words.py
    python scripts/gen_safety_words.py --check  # exit 1 when safety_words.py is out of date (CI / pre-commit)

The test services/voice-agent/test_safety_words_sync.py runs the same check, so a phrase added to distress.py
without regenerating fails the suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "services" / "voice-agent" / "safety_words.py"
REASONING = ROOT / "services" / "reasoning"

HEADER = '''"""Safety words the voice agent keeps locally so media mode never needs a service to protect her.

GENERATED FILE - DO NOT EDIT. Source of truth: services/reasoning/reasoning_svc/distress.py.
Regenerate with `python scripts/gen_safety_words.py`; test_safety_words_sync.py fails when this file is stale.

No imports from other services (they share contracts, not code), so it works with reasoning and core-api down.
Deliberately recall-biased: a false positive only passes a sentence on to reasoning.
"""

import re
import unicodedata
'''

LOGIC = '''

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_PUNCT = re.compile(r"[,.?!।;\\"“”‘’()\\[\\]{}]+")
_FOLD = str.maketrans({"ँ": "ं", "ि": "ी", "ु": "ू"})
_DROP = dict.fromkeys([0x200C, 0x200D, 0x093C])  # ZWNJ, ZWJ, nukta
_E_TR = str.maketrans({"ॅ": "ै", "े": "ै", "ॲ": "अ", "ऍ": "अ"})
_TRAILING_HALANT = re.compile("्(?=\\\\s|$)")


def normalize(text: str) -> str:
    t = _PUNCT.sub(" ", text.lower().translate(_DEVANAGARI_DIGITS))
    return re.sub(r"\\s+", " ", t).strip()


def fold(text: str) -> str:
    return unicodedata.normalize("NFC", normalize(text)).translate(_DROP).translate(_FOLD)


def efold(text: str) -> str:
    return _TRAILING_HALANT.sub("", fold(text).translate(_E_TR).replace("-", " ").replace("_", " "))


def has_any(norm: str, phrases: tuple[str, ...]) -> bool:
    padded = f" {norm} "
    return any(f" {p} " in padded for p in phrases)


def _compile(patterns: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p) for p in patterns)


_DISTRESS_RE = _compile(_DISTRESS_PATTERNS)
_EMERGENCY_RE = _compile(_EMERGENCY_PATTERNS)
_SPACED_RE = _compile(_SPACED_PATTERNS)
_COMPACT_RE = _compile(_COMPACT_PATTERNS)
_PAST_MARK = re.compile(_PAST_MARK_PATTERN)
_NOW_MARK = re.compile(_NOW_MARK_PATTERN)
_DISTRESS_FOLDED = tuple(fold(p) for p in DISTRESS_PHRASES)
_EMERGENCY_FOLDED = tuple(fold(p) for p in EMERGENCY_PHRASES)

SAFETY_PHRASES: tuple[str, ...] = EMERGENCY_PHRASES + DISTRESS_PHRASES


def _word_regex(words: tuple[str, ...]) -> re.Pattern[str]:
    parts = []
    for w in words:
        e = re.escape(efold(w))
        parts.append(rf"(?<![a-z0-9]){e}(?![a-z0-9])" if w.isascii() else rf"(?<!\\S){e}")
    return re.compile("|".join(parts))


_FAILSAFE_RE = _word_regex(FAILSAFE_WORDS)


def is_distress(text: str) -> bool:
    folded = fold(text)
    return has_any(folded, _DISTRESS_FOLDED) or any(p.search(folded) for p in _DISTRESS_RE)


def loanword_emergency(text: str) -> bool:
    spaced = efold(text)
    compact = re.sub(r"\\s+", "", spaced)
    if _PAST_MARK.search(spaced) and not _NOW_MARK.search(spaced):  # a story about the past is not an emergency
        return False
    return any(p.search(spaced) for p in _SPACED_RE) or any(p.search(compact) for p in _COMPACT_RE)


def is_emergency(text: str) -> bool:
    folded = fold(text)
    basic = has_any(folded, _EMERGENCY_FOLDED) or any(p.search(folded) for p in _EMERGENCY_RE)
    return basic or loanword_emergency(text)


def is_safety_phrase(text: str) -> bool:
    return is_emergency(text) or is_distress(text) or bool(_FAILSAFE_RE.search(efold(text)))
'''


def _tuple(name: str, items: tuple[str, ...] | list[str], annotation: str = "tuple[str, ...]") -> str:
    lines = [f"{name}: {annotation} = ("]
    lines += [f"    {item!r}," for item in items]
    lines.append(")")
    return "\n".join(lines)


def render() -> str:
    sys.path.insert(0, str(REASONING))
    from reasoning_svc import distress as d  # noqa: PLC0415 - path set just above

    parts = [
        HEADER.rstrip(),
        _tuple("EMERGENCY_PHRASES", d.EMERGENCY_PHRASES),
        _tuple("DISTRESS_PHRASES", d.DISTRESS_PHRASES),
        _tuple("_EMERGENCY_PATTERNS", [p.pattern for p in d._EMERGENCY_PATTERNS]),
        _tuple("_DISTRESS_PATTERNS", [p.pattern for p in d._PATTERNS]),
        _tuple("_SPACED_PATTERNS", [p.pattern for p in d._SPACED]),
        _tuple("_COMPACT_PATTERNS", [p.pattern for p in d._COMPACT]),
        f"_PAST_MARK_PATTERN = {d._PAST_MARK.pattern!r}",
        f"_NOW_MARK_PATTERN = {d._NOW_MARK.pattern!r}",
        _tuple("FAILSAFE_WORDS", d._FAILSAFE_WORDS),
    ]
    return "\n\n".join(parts) + "\n" + LOGIC


def main(argv: list[str]) -> int:
    new = render()
    if "--check" in argv:
        old = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if old != new:
            print("safety_words.py is out of date: run `python scripts/gen_safety_words.py`")
            return 1
        print("safety_words.py is up to date")
        return 0
    TARGET.write_text(new, encoding="utf-8", newline="\n")
    print(f"wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
