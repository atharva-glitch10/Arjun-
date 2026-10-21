"""Distress check - runs on EVERY turn and overrides everything else (temperature-free, rules only).

Deliberately recall-biased: a false positive costs a gentle check-in; a false negative is unsafe.
This is a keyword safety net, not a clinical classifier - it never diagnoses.
"""

import re
import unicodedata

from .textutil import has_any, normalize

# Phrases are matched as whole tokens on normalised text (see textutil.has_any).
DISTRESS_PHRASES: tuple[str, ...] = (
    # English
    "kill myself", "want to die", "wanna die", "end my life", "no reason to live",
    "nothing to live for", "hopeless", "i give up", "better off dead", "hurt myself",
    "suicide", "someone is hurting me", "he hits me", "she hits me", "they hit me",
    "i am afraid", "i am scared", "i'm scared", "i'm afraid", "nobody cares",
    # Hindi (Devanagari + roman)
    "मरना चाहता हूँ", "मरना चाहती हूँ", "जीने का मन नहीं", "जीने की इच्छा नहीं", "आत्महत्या",
    "मुझे डर लग रहा है", "मुझे मारते हैं", "कोई मुझे मारता है", "सब खत्म",
    "marna chahta hoon", "marna chahti hoon", "jeene ka mann nahi", "mujhe dar lag raha hai",
    "mujhe maarte hain", "koi mujhe maarta hai", "sab khatam",
    # Marathi (Devanagari + roman)
    "मला मरायचं आहे", "मला मरावंसं वाटतं", "जगायची इच्छा नाही", "जगावंसं वाटत नाही",
    "आत्महत्या करावी", "मला भीती वाटतेय", "मला भीती वाटते", "मला कोणी मारतं",
    "मला कुणी मारतं", "सगळं संपलं", "सगळं संपवावं",
    "mala marayche aahe", "mala marayacha aahe", "mala maravasa vatta", "jagaychi iccha nahi",
    "jagavasa vatat nahi", "mala bhiti vatte", "mala bhiti vatate", "mala koni marto",
    "mala koni marte", "mala kuni marto", "sagla sampla", "sagla sampavave",
)


_FOLD = str.maketrans({"ँ": "ं", "ि": "ी", "ु": "ू"})
_DROP = dict.fromkeys([0x200C, 0x200D, 0x093C])  # ZWNJ, ZWJ, nukta


def fold(text: str) -> str:
    """Normalise spelling variants that speech-to-text produces for the same utterance:
    chandrabindu/anusvara, short/long i and u, nukta, zero-width joiners."""
    return unicodedata.normalize("NFC", normalize(text)).translate(_DROP).translate(_FOLD)


# Stem patterns so spelling/inflection variants still match. UNVERIFIED lexicon: written without
# a native speaker or real ASR output; it must be reviewed and extended before any public demo.
# Deliberately left out: "मरायला" (idiom "no time to die"), so "मला मरायला वेळ नाही" is not flagged.
_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        # Marathi (Devanagari)
        r"(?<!\S)मरा(?:यच|वंस|वेस)\S*",
        r"(?<!\S)जगा(?:यच|यला|वंस|वेस)\S*(?:\s+\S+){0,2}\s+(?:नाही|नको)(?!\S)",
        # Hindi (Devanagari)
        r"(?<!\S)मर(?:जा)?(?:ना|ने)\s+चाह\S*",
        r"(?<!\S)मर\s+जा(?:ऊं|ऊंगा|ऊंगी|ना\s+चाह\S*)",
        r"(?<!\S)जी(?:ना|ने)\s+(?:का\s+मन\s+)?(?:नहीं|नही)(?!\S)",
        r"(?<!\S)जीवन\s+(?:खत्म|समाप्त|संपव)\S*",
        # roman Marathi / Hindi
        r"\bmaray(?:ch|ach|avas|aves)\w*",
        r"\bmarun\s+(?:jain|jau|jaycha|jav)\w*",
        r"\bmar\s+jau\w*",
        r"\bmar(?:na|ne)\s+chah\w*",
        r"\bmar\s+ja+n[ae]\s+chah\w*",
        r"\bjag(?:aych|ayach|avas|aves)\w*\s+(?:\w+\s+){0,2}(?:nahi|nako)\b",
        r"\bjee?n[ae]\s+(?:ka\s+man+\s+)?nahi\b",
        r"\bjeevan\s+sampav\w*",
        # English
        r"\b(?:do not|don.?t)\s+want\s+to\s+(?:live|be\s+alive|be\s+here|go\s+on|exist)\b",
        r"\bwant\s+to\s+(?:end|finish)\s+(?:it|everything)\b",
        r"\bend\s+it\s+all\b",
        r"\b(?:can.?t|cannot)\s+go\s+on\b",
        r"\btak(?:e|ing)\s+my\s+own\s+life\b",
        r"\bno\s?one\s+(?:would|will)\s+miss\s+me\b",
        r"\bbetter\s+off\s+without\s+me\b",
        r"\bwish\s+i\s+(?:was|were)\s+dead\b",
        r"\bwant\s+to\s+disappear\b",
    )
)
_PHRASES = tuple(fold(p) for p in DISTRESS_PHRASES)


def is_distress(text: str) -> bool:
    folded = fold(text)
    return has_any(folded, _PHRASES) or any(p.search(folded) for p in _PATTERNS)
