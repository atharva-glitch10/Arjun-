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


# ---- COPY of reasoning/distress.py: English loanwords and speech-to-text spellings (2026-11-03) ---------------------
# ---- English loanwords and speech-to-text spellings (2026-11-03) ------------------------------------------------------
# "मला हार्ट अटॅक येतोय" got a chatty LLM reply because only the Latin "heart attack" was in the lexicon, while a
# Marathi recogniser writes loanwords in Devanagari, spaced or not, with अटॅक / अटैक / अटेक / अॅटॅक spellings.
# Matching runs on efold(): fold() + chandra-e / e -> ai, no word-final halant. Every pattern below is written in
# natural spelling and folded the same way (_epat), exactly like the symptom patterns. Two views of the text are
# searched: the spaced words, and the same text with all spaces removed ("हार्टअटॅक", "heartattack").
# UNVERIFIED lexicon (no native speaker, little real ASR output): recall-biased, to be reviewed before a public demo.
_E_TR = str.maketrans({"ॅ": "ै", "े": "ै", "ॲ": "अ", "ऍ": "अ"})
_TRAILING_HALANT = re.compile("्(?=\\s|$)")


def efold(text: str) -> str:
    return _TRAILING_HALANT.sub("", fold(text).translate(_E_TR).replace("-", " ").replace("_", " "))


def _epat(p: str) -> re.Pattern[str]:
    return re.compile(unicodedata.normalize("NFC", p).translate(_DROP).translate(_FOLD).translate(_E_TR))


_NOT_NEGATED = r"(?!\s+(?:नाही|नको|नहीं|नही))"
_VERB_ATTACK = r"(?:आला|आलाय|आली|आलं|आलंय|येतोय|येतो|येतेय|येते|येतंय|येत\s+आहे|आ\s+गया|आया|आ\s+रहा|aala|aalay|yetoy|yete)\S*"
_SPACED = tuple(
    _epat(p)
    for p in (
        # heart attack with the verb and without the word "heart": "attack आला", "अटॅक येतोय"
        rf"(?<!\S)(?:attack|atack|atak|अटॅक|अॅटॅक|एटॅक)\s+{_VERB_ATTACK}",
        # heart pain
        rf"(?<!\S)(?:हृदय|हार्ट|heart)\S*\s+(?:\S+\s+)?(?:दुख|दुःख|कळ|pain|hurts?|aches?)\S*{_NOT_NEGATED}",
        # chest
        rf"(?<!\S)छाती\S*\s+(?:\S+\s+)?(?:दुख|दुःख|कळ|दाब|दडपण|जड|आवळ|त्रास|धडधड)\S*{_NOT_NEGATED}",
        r"\bchest\s+(?:\w+\s+)?(?:pain|pains|hurts?|aches?|tight|heavy)\b",
        r"\bpain\s+in\s+(?:my\s+|the\s+)?chest\b",
        r"\bchest\s+(?:\S+\s+)?(?:दुख|दुःख|कळ|दाब|जड|त्रास)\S*",
        # blood pressure high / sugar low (the family-set readings flow is separate and frozen)
        r"(?<!\S)(?:bp|बीपी|बी\s+पी|ब्लड\s+प्रेशर|blood\s+pressure|रक्तदाब)\s+(?:\S+\s+){0,3}(?:high|हाय|वाढ\S*|जास्त|कमी|low|लो|खाली)(?!\S)(?!\s+(?:होत))",
        r"(?<!\S)(?:sugar|शुगर)\s+(?:\S+\s+)?(?:low|लो|कमी|खाली|drop\S*|उतर\S*)(?!\S)",
        r"(?<!\S)(?:low|लो)\s+(?:sugar|शुगर)(?!\S)",
        # stroke
        r"(?<!\S)(?:stroke|स्ट्रोक|लकवा|लकवे|पक्षाघात|पॅरालिसिस|पैरालिसिस|पैरालीसिस|paralysis|paralyzed|paralysed)(?!\S)",
        r"(?<!\S)तोंड\s+वाकड\S*",
        r"(?<!\S)(?:हात|पाय)\s+(?:लुळा|लुळे|उचलता\s+येत\s+नाही)\S*",
        r"(?<!\S)बोलता\s+येत\s+नाही",
        # fainting
        r"(?<!\S)(?:faint(?:ed|ing)?|unconscious|blackout|black\s+out|passed\s+out|भोवळ\S*|बेशुद्ध\S*|बेहोश\S*)(?!\S)",
        r"(?<!\S)चक्कर\s+(?:येऊन|आऊन|आकर)\s+(?:\S+\s+)?पडल\S*",
        # breathing
        r"(?<!\S)श्वास\S*\s+घेता\s+येत\s+(?:नाही|नही|नहीं)\S*",
        rf"(?<!\S)श्वास\S*\s+(?:\S+\s+)?(?:घेताना|अडक|कोंड|फुल|लाग|गुदमर|त्रास)\S*{_NOT_NEGATED}",
        rf"(?<!\S)दम\s+(?:\S+\s+)?(?:लाग|कोंड|घुट|अडक)\S*{_NOT_NEGATED}",
        r"(?<!\S)(?:सांस|साँस)\s+(?:\S+\s+)?(?:फूल|फुल|अटक)\S*",
        r"\b(?:breathless\w*|short\s+of\s+breath|(?:difficulty|trouble|problem|hard)\s+(?:in\s+|to\s+)?breath\w*|breath\w*\s+(?:problem|trouble|difficulty|issue))\b",
        r"(?<!\S)(?:ब्रीदिंग|ब्रिदिंग|breathing)\s+(?:\S+\s+)?(?:प्रॉब्लेम|प्रोब्लेम|त्रास|problem|trouble)",
        # a fall NOW (spelling variants of the original pattern: पडलोय, पडलीय, खाली पडले, घसरून पडलो)
        r"(?<!\S)(?:मी\s+)?(?:खाली\s+)?पडल(?:े|ो|ी)(?:य|ये|ंय)?(?:\s+आहे)?(?!\s*(?:होत|होतं))(?:\s|$)",
        r"(?<!\S)(?:घसरून|तोल\s+जाऊन|तोल\s+गेला)\S*\s+(?:\S+\s+)?पडल\S*",
        r"\b(?:i\s+)?(?:have\s+)?(?:fell|fallen)\s+(?:down|over)\b",
        # blood
        rf"(?<!\S)रक्त\S*\s+(?:\S+\s+)?(?:येत|पडत|निघत|वाहत|आल)\S*{_NOT_NEGATED}",
        r"(?<!\S)रक्तस्(?:त्)?राव\S*",
        r"\b(?:bleeding|blood\s+(?:is\s+)?(?:coming|flowing|everywhere))\b",
    )
)
# Searched with the spaces removed: "हार्टअटॅक", "heartattack", "HeartAttack", "चेस्टपेन", "chestpain".
_COMPACT = tuple(
    _epat(p)
    for p in (
        r"h(?:ea?|aa?)rtat+a?c?k",  # heart/hart/haart + attack/atack/atak
        r"हा?र्?ट[अएऐ]ै?ट[ैा]?क",  # हार्ट + अटॅक / अटैक / अटेक / अॅटॅक / एटॅक
        r"chestpains?",
        r"चेस्ट(?:पेन|पैन)",
        r"paininmychest|paininthechest",
    )
)
_PAST_MARK = re.compile(r"(?<!\S)(?:होता|होतं|होते|होती|होतो)(?!\S)")
_NOW_MARK = re.compile(r"(?<!\S)(?:येतोय|येतो|येतेय|येते|येतंय|येत|आत्ता|आता|now|right|चाललाय|चाललंय)\S*")


def loanword_emergency(text: str) -> bool:
    spaced = efold(text)
    compact = re.sub(r"\s+", "", spaced)
    past_story = bool(_PAST_MARK.search(spaced)) and not _NOW_MARK.search(spaced)  # "वडिलांना ... आला होता"
    if past_story:  # "त्यांना हार्ट अटॅक आला होता": a story about the past is not an emergency now
        return False
    return any(p.search(spaced) for p in _SPACED) or any(p.search(compact) for p in _COMPACT)



# The words the reasoning service sends to its second safety layer (and treats as an emergency if that check fails).
# Media mode lets them through to reasoning too: it decides, the player never swallows them.
_FAILSAFE_WORDS = ("attack", "atak", "atack", "अटैक", "छाती", "श्वास", "बेशुद्ध", "stroke", "स्ट्रोक", "chest")

def _word_regex(words: tuple[str, ...]) -> re.Pattern[str]:
    """Latin words must be whole words ("atak" must not be found inside "ata kay"); a Devanagari word matches at the
    start of a token, so its inflections still match ("छातीत", "श्वासाचा")."""
    parts = []
    for w in words:
        e = re.escape(efold(w))
        parts.append(rf"(?<![a-z0-9]){e}(?![a-z0-9])" if w.isascii() else rf"(?<!\S){e}")
    return re.compile("|".join(parts))


_FAILSAFE_RE = _word_regex(_FAILSAFE_WORDS)


def is_safety_phrase(text: str) -> bool:
    folded = fold(text)
    return (
        any(f" {p} " in f" {folded} " for p in _FOLDED_SAFETY)
        or loanword_emergency(text)
        or bool(_FAILSAFE_RE.search(efold(text)))
    )
