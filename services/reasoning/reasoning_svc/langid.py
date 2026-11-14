"""Which language is this text in? Script first, then word markers for the Devanagari pair Marathi / Hindi.

ONE helper for reasoning (reply guard, reply-language choice) and voice-agent (refining Prisma's hi / mr label). This file is the
canonical copy; `services/reasoning/reasoning_svc/langid.py` and `services/voice-agent/langid.py` are byte-identical copies
(a test fails if they drift), because each service is deployed on its own.

Pure Python, no network. The word lists are UNVERIFIED by a native speaker: they were written from common function words and
verb endings, then checked on ~70 sentences of each language including code-mixed ones (tests)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# scripts that belong to exactly one Gnani language
_SCRIPTS = (
    (0x0980, 0x09FF, "bn"), (0x0A00, 0x0A7F, "pa"), (0x0A80, 0x0AFF, "gu"), (0x0B80, 0x0BFF, "ta"),
    (0x0C00, 0x0C7F, "te"), (0x0C80, 0x0CFF, "kn"), (0x0D00, 0x0D7F, "ml"),
)
_DEVANAGARI = (0x0900, 0x097F)

_DROP = dict.fromkeys([0x200C, 0x200D, 0x093C])  # ZWNJ, ZWJ, nukta
_FOLD = str.maketrans({"ँ": "ं"})  # chandrabindu -> anusvara, so "हूँ" and "हूं" are one spelling
_WORD = re.compile(r"[ऀ-ॿ]+")

# Marathi-only words and endings (never Hindi)
MR_WORDS = frozenset("""
मी आहे आहेत आहात आहोत नाही नाहीत नाहीये नका नको तुम्ही तुमचा तुमची तुमचं तुमचे तुमच्या तुमच्याशी तुमच्याकडे तुमच्यासाठी तुला तुझा तुझी
तुझं माझा माझी माझं माझे माझ्या माझ्याशी मला आम्ही आपल्या आपला आपली आपलं काय कसं कसे कसा कशी कुठे कधी केव्हा कोण कोणी असं तसं इथे तिथे
बोलतो बोलते बोलू बोला बोलणार बोलायचं बोलायचंय करतो करते करायचं करायचंय सांगा सांगतो सांगते सांगू ऐकतो ऐकते हिंदीतच हिंदीत मराठीत
मराठीतच इंग्रजीत आणि पण होय छान बरं सगळं सगळे खूप फार आता मध्ये साठी वाटतं वाटतंय चाललंय चाललं झालं झाली झाले होतं होतो होते असते
असतो आलो गेलो गेले जातो जाते जातोय येतो येते येतोय घेतो घेतली दिलं दिली म्हणून म्हणजे म्हणाला म्हणाली म्हणालात म्हणतात आवडतं आवडतो हवं हवा
हवी पाहिजे पाहिजेत लागतं लागतो नक्की बरोबर उद्या परवा सकाळी संध्याकाळी रात्री दुपारी जेवण जेवलो जेवलात झोप
दाखवा लावा लाव मग करा का ना
""".split())
_MR_ENDING = re.compile(r"(?:तोय|तंय|ायचं|ायचंय|ायला|ल्यावर|ऱ्या|ाऱ्या|तोस|तेस|लात|णार|ची|चा|चे)$")

# Hindi-only words (never Marathi)
HI_WORDS = frozenset("""
मैं मुझे मुझसे मेरा मेरी मेरे हम हमें हमारा हमारी आप आपको आपसे आपका आपकी आपके तुम तुम्हें तुम्हारा तुम्हारी तुम्हारे तुझे है हैं हूं था
थी थे नहीं मत क्या कैसे कैसा कैसी कहां कब कौन क्यों और लेकिन बहुत अभी बात करना करनी करो करें करता करती करूंगा करूंगी बोलो बोलिए बोलता
बोलती बताओ बताइए बताना सुनो सुनिए चाहिए चाहता चाहती में रहा रही रहे गया गई गए आया आई आए लगा लगी लिए इसलिए यह वह इस उस ये वे कुछ सब
अच्छा जी हां जरा ज़रा सकता सकती सकते मिलेगा होगा होगी होंगे कहते कहता कहती देखो देखिए समझ समझा समझी बताऊंगा कीजिए कीजिये दीजिए
लगाओ लगाइए सुबह शाम रात दोपहर खाना खाया पिया नींद
""".split())


@dataclass(frozen=True)
class Guess:
    lang: str  # mr | hi | en | bn | gu | kn | ml | pa | ta | te | "" (no letters)
    confidence: float  # 0..1
    mr: int = 0
    hi: int = 0


def _norm_token(tok: str) -> str:
    return unicodedata.normalize("NFC", tok).translate(_DROP).translate(_FOLD)


def devanagari_scores(text: str) -> tuple[int, int]:
    """(Marathi evidence, Hindi evidence): how many words are typical of each, "आज" and other shared words count for neither."""
    mr = hi = 0
    for raw in _WORD.findall(unicodedata.normalize("NFC", text)):
        tok = _norm_token(raw)
        if tok in MR_WORDS or _MR_ENDING.search(tok):
            mr += 1
        elif tok in HI_WORDS:
            hi += 1
    return mr, hi


def classify(text: str, default: str = "") -> Guess:
    """The language of `text`. Script decides everything except Marathi vs Hindi (word markers) and Latin (English).
    When the Devanagari evidence is a tie, `default` (the profile / Prisma label) breaks it, else Marathi."""
    letters = [c for c in text if c.isalpha() or (ord(c) >= 0x0900 and unicodedata.category(c).startswith("M"))]  # + vowel signs
    if not letters:
        return Guess("", 0.0)
    counts: dict[str, int] = {}
    for c in letters:
        cp = ord(c)
        if _DEVANAGARI[0] <= cp <= _DEVANAGARI[1]:
            counts["dev"] = counts.get("dev", 0) + 1
            continue
        for lo, hi, lang in _SCRIPTS:
            if lo <= cp <= hi:
                counts[lang] = counts.get(lang, 0) + 1
                break
        else:
            if c.isascii():
                counts["latin"] = counts.get("latin", 0) + 1
    if not counts:
        return Guess("", 0.0)
    # A Latin loanword or brand ("recipe", "YouTube") cannot outvote the spoken Indic script.
    non_latin = {script: count for script, count in counts.items() if script != "latin"}
    considered = non_latin or counts
    top, n = max(considered.items(), key=lambda kv: kv[1])
    share = n / sum(considered.values())
    if top == "latin":
        return Guess("en", round(share, 2))
    if top != "dev":
        return Guess(top, round(share, 2))
    mr, hi = devanagari_scores(text)
    if mr == hi == 0:
        return Guess(default if default in ("mr", "hi") else "mr", 0.0, mr, hi)
    lang = "mr" if mr and mr >= hi else "hi"
    return Guess(lang, round(abs(mr - hi) / (mr + hi), 2), mr, hi)


def confident(guess: Guess) -> bool:
    """Enough evidence to overrule a label: another script, or a Devanagari margin of at least two words."""
    if guess.lang in ("mr", "hi"):
        return (guess.lang == "mr" and guess.mr > 0 and guess.mr >= guess.hi) or abs(guess.mr - guess.hi) >= 2
    return bool(guess.lang) and guess.confidence >= 0.6


def matches(text: str, expected: str) -> bool:
    """True when `text` is (or may be) in `expected`: an unsure or too-short text never counts as a mismatch, and names
    in the other script do not matter (the majority script decides)."""
    guess = classify(text, default=expected)
    if not guess.lang:
        return True
    if guess.lang in ("mr", "hi") and expected in ("mr", "hi"):
        return guess.lang == expected or not confident(guess)
    if guess.lang == expected:
        return True
    return guess.confidence < 0.5
