"""Safety words the voice agent keeps locally so media mode never needs a service to protect her.

COPY, not import: services share contracts, not code. The source of truth is
`services/reasoning/reasoning_svc/distress.py` (EMERGENCY_PHRASES / DISTRESS_PHRASES). If a phrase is added
there, add it here too. Deliberately recall-biased: a false positive only passes a sentence on to reasoning.
"""

import re
import unicodedata

# Physical emergency, checked before emotional distress. "मी पडले" is the distress.py fall PATTERN, copied
# here as a phrase because playback must never swallow "मी पडले".
EMERGENCY_PHRASES: tuple[str, ...] = (
    # English
    "chest pain", "my chest hurts", "pain in my chest", "can't breathe", "cannot breathe",
    "cant breathe", "i can't breathe", "unable to breathe", "i have fallen", "i fell down",
    "can't get up", "cannot get up", "heart attack", "stroke", "i am bleeding", "i'm bleeding",
    "i fainted", "i am fainting", "call ambulance", "ambulance", "i feel dizzy", "i am dizzy", "feeling dizzy",
    # Marathi (Devanagari)
    "छातीत दुखतंय", "छातीत दुखत आहे", "छातीत दुखते", "छातीत कळ", "श्वास घेता येत नाही",
    "श्वास लागतोय", "दम लागतोय", "दम लागला", "उठता येत नाही", "चक्कर येतेय", "चक्कर येत आहे",
    "बेशुद्ध", "रक्त येतंय", "खूप रक्त", "हृदयविकार", "रुग्णवाहिका",
    # a fall right now (the source keeps this as a pattern)
    "मी पडले", "मी पडलो", "मी पडली", "mi padle", "mi padlo", "mi padli",
    # dizziness is emergency-level too (2026-10-31)
    "चक्कर आली", "चक्कर आले", "चक्कर आल्यासारखं", "चक्कर येते", "चक्कर आ रही",
    # Marathi (roman)
    "chhatit dukhtay", "chatit dukhtay", "chhatit dukhat aahe", "shwas gheta yet nahi",
    "swas gheta yet nahi", "dam lagtoy", "uthta yet nahi", "chakkar yetey", "chakkar yet aahe",
    "rakta yetay", "khup rakta", "chakkar aali", "chakkar yete",
    # Hindi (Devanagari)
    "सीने में दर्द", "छाती में दर्द", "सांस नहीं ले पा", "साँस नहीं ले पा", "सांस नहीं आ रही",
    "उठ नहीं पा", "चक्कर आ रहा", "बेहोश", "खून बह रहा",
    # Hindi (roman)
    "seene mein dard", "seene me dard", "chhati mein dard", "saans nahi le pa", "sans nahi aa rahi",
    "uth nahi pa", "chakkar aa raha", "behosh", "khoon beh raha",
)

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

SAFETY_PHRASES: tuple[str, ...] = EMERGENCY_PHRASES + DISTRESS_PHRASES

_PUNCT = re.compile(r"[,.?!।;:\"“”‘’()\[\]{}]+")
_FOLD = str.maketrans({"ँ": "ं", "ि": "ी", "ु": "ू"})
_DROP = dict.fromkeys([0x200C, 0x200D, 0x093C])  # ZWNJ, ZWJ, nukta


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", _PUNCT.sub(" ", text.lower())).strip()


def fold(text: str) -> str:
    """Same spelling folding as reasoning: anusvara, short/long i and u, nukta, zero-width joiners."""
    return unicodedata.normalize("NFC", normalize(text)).translate(_DROP).translate(_FOLD)


_FOLDED_SAFETY = tuple(fold(p) for p in SAFETY_PHRASES)


def has_phrase(norm: str, phrase: str) -> bool:
    return f" {fold(phrase)} " in f" {norm} "


def is_safety_phrase(text: str) -> bool:
    folded = fold(text)
    return any(f" {p} " in f" {folded} " for p in _FOLDED_SAFETY)
