"""Distress check - runs on EVERY turn and overrides everything else (temperature-free, rules only).

Deliberately recall-biased: a false positive costs a gentle check-in; a false negative is unsafe.
This is a keyword safety net, not a clinical classifier - it never diagnoses.
"""

import re
import unicodedata

from . import safety_langs
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
    return has_any(folded, _PHRASES) or any(p.search(folded) for p in _PATTERNS) or safety_langs.is_distress(text)


# ---- Physical emergency (checked BEFORE emotional distress) -------------------------------------
# Body/danger words: chest pain, breathing, a fall right now, fainting, heavy bleeding.
# UNVERIFIED lexicon (same status as above): needs native-speaker review and real ASR output.
# Recall-biased, but past-tense story phrasing ("मी लहानपणी पडले होते" / "padle hote") is excluded
# so childhood stories don't trigger an emergency.
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

_EMERGENCY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        # "मी पडले / पडलो / पडले आहे" now - but not "पडले होते" (a story)
        r"(?<!\S)(?:मी\s+)?पडल(?:े|ो|ी)(?:\s+आहे)?(?!\s*(?:होत|होतं))(?:\s|$)",
        r"\bmi\s+padl(?:e|o|i)\b(?!\s+hot)",
        # written in fold()ed spelling (ि -> ी), because patterns run on folded text
        r"(?<!\S)(?:मैं\s+)?गीर\s+ग(?:या|ई|यी)(?!\s+था|\s+थी)",
        r"\b(?:main\s+)?gir\s+ga(?:ya|yi|i)\b(?!\s+th)",
        r"\bi\s+(?:just\s+)?fell\b",
    )
)
_EMERGENCY_FOLDED = tuple(fold(p) for p in EMERGENCY_PHRASES)


def _is_emergency_basic(text: str) -> bool:
    folded = fold(text)
    return (
        has_any(folded, _EMERGENCY_FOLDED)
        or any(p.search(folded) for p in _EMERGENCY_PATTERNS)
        or safety_langs.is_emergency(text)  # bn gu kn ml pa ta te (UNVERIFIED lexicon)
    )


def is_emergency(text: str) -> bool:
    """A physical emergency by RULES: the original lexicon plus the English loanwords and STT spellings."""
    return _is_emergency_basic(text) or loanword_emergency(text)


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


# ---- Second layer: a health or body word that no rule recognised --------------------------------------------------------
# The turn goes to a strict-JSON LLM check (2 s). If the LLM is unavailable, the FAIL-SAFE words below are treated as an
# emergency. Recall-biased on purpose: a false alert costs a phone call; a missed heart attack costs far more.
_HEALTH_WORDS = (
    "छाती", "हृदय", "हार्ट", "heart", "chest", "श्वास", "सांस", "साँस", "दम", "बेशुद्ध", "बेहोश", "भोवळ", "चक्कर",
    "रक्त", "खून", "blood", "bleeding", "अटैक", "अटॅक", "attack", "atak", "atack", "stroke", "स्ट्रोक", "लकवा", "paralysis",
    "बीपी", "bp", "शुगर", "sugar", "दुखत", "वेदना", "त्रास", "पडल", "पडून", "fell", "fall", "faint",
    "pain", "breath", "dizzy", "unwell", "बरं वाटत नाही", "ambulance", "रुग्णवाहिका"
)
_FAILSAFE_WORDS = ("attack", "atak", "atack", "अटैक", "छाती", "श्वास", "बेशुद्ध", "stroke", "स्ट्रोक", "chest")
def _word_regex(words: tuple[str, ...]) -> re.Pattern[str]:
    """Latin words must be whole words ("atak" must not be found inside "ata kay"); a Devanagari word matches at the
    start of a token, so its inflections still match ("छातीत", "श्वासाचा")."""
    parts = []
    for w in words:
        e = re.escape(efold(w))
        parts.append(rf"(?<![a-z0-9]){e}(?![a-z0-9])" if w.isascii() else rf"(?<!\S){e}")
    return re.compile("|".join(parts))


_HEALTH_RE = _word_regex(_HEALTH_WORDS)
_FAILSAFE_RE = _word_regex(_FAILSAFE_WORDS)


def has_health_word(text: str) -> bool:
    return bool(_HEALTH_RE.search(efold(text)))


def has_failsafe_word(text: str) -> bool:
    return bool(_FAILSAFE_RE.search(efold(text)))


# ---- A reply that must never be spoken: medical advice for a heart attack, chest pain or stroke --------------------
_CARDIAC = tuple(
    efold(w)
    for w in (
        "हार्ट अटॅक", "हार्टअटॅक", "heart attack", "heartattack", "छातीत दुख", "छातीत कळ", "chest pain", "stroke",
        "स्ट्रोक", "लकवा", "हृदयविकार", "हृदयाचा झटका", "हार्ट अटैक", "दिल का दौरा", "सीने में दर्द",
    )
)
_ADVICE = tuple(
    efold(w)
    for w in (
        "aspirin", "एस्प्रिन", "ॲस्पिरिन", "अस्पिरिन", "गोळी", "गोली", "औषध घ्या", "दवा लें", "tablet", "medicine",
        "झोपा", "झोपून", "बसा", "बसून", "आराम करा", "विश्रांती", "दीर्घ श्वास", "खोल श्वास", "deep breath", "breathe deeply",
        "lie down", "sit down", "rest", "relax", "पाणी प्या", "drink water", "शांत राहा", "आराम करें", "लेट जाइए", "बैठ जाइए",
        "take a", "take an", "take two", "घ्या",
    )
)


def mentions_cardiac(text: str) -> bool:
    spaced = efold(text)
    compact = re.sub(r"\s+", "", spaced)
    return any(w in spaced or w.replace(" ", "") in compact for w in _CARDIAC) or loanword_emergency(text)


def gives_medical_advice(reply: str) -> bool:
    spaced = efold(reply)
    return any(w in spaced for w in _ADVICE)


# ---- Loneliness (NOT a safety check: it never overrides a care command or a pending question) -----------
# "मला एकटं वाटतं", "akela mehsoos hota hai", "I feel lonely". Arjun answers warmly, offers to call someone
# in the family (a bridge to people, CLAUDE.md principle) and, ONLY with the family-alert consent, tells the
# family once a day that she said she feels lonely (never her words).
# UNVERIFIED lexicon, same status as the two above: written without a native speaker or real Prisma output.
LONELY_PHRASES: tuple[str, ...] = (
    # English
    "i feel lonely", "i am lonely", "i'm lonely", "feeling lonely", "so lonely", "very lonely", "all alone",
    "i feel alone", "i am all alone", "loneliness", "i miss my family", "i miss my children", "i miss my son",
    "i miss my daughter",
    # Marathi (Devanagari)
    "एकटं वाटतं", "एकटं वाटतंय", "एकटं वाटत आहे", "एकटेपणा", "एकटेपणा वाटतो", "कोणी बोलत नाही",
    "कुणी बोलत नाही", "कोणी भेटायला येत नाही", "कुणी भेटायला येत नाही", "माझ्याशी कोणी बोलत नाही",
    # Marathi (roman)
    "ekta vatta", "ekta vattay", "ekta vatat aahe", "ekatepana", "ektepana", "koni bolat nahi",
    "kuni bolat nahi", "koni bhetayla yet nahi",
    # Hindi (Devanagari)
    "अकेलापन", "अकेला महसूस", "अकेली महसूस", "अकेला लगता", "अकेली लगती", "कोई बात नहीं करता",
    "कोई मिलने नहीं आता", "मुझसे कोई बात नहीं करता",
    # Hindi (roman)
    "akelapan", "akela mehsoos", "akeli mehsoos", "akela lagta", "akeli lagti", "koi baat nahi karta",
    "koi milne nahi aata",
)

_LONELY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        # Marathi: एकटं / एकटा / एकटी + वाटतं / आहे (now), not "एकटी होते" (a story about the past)
        r"(?<!\S)एकट(?:ं|ा|ी|े)\s+(?:वाट|आह)\S*",
        r"\bekt(?:a|i|e)\s+(?:vat|aah)\w*",
        # Hindi: अकेला / अकेली + महसूस / लग / हूँ (folded: ँ -> ं); not "अकेले जाऊँगी" (going alone)
        r"(?<!\S)अकेल(?:ा|ी|े)\s+(?:महसूस|लग|हूं|हू)\S*",
        r"\bakel(?:a|i|e)\s+(?:mehsoos|mahsoos|lag|hoon|hun|hu)\w*",
        # English
        r"\blonel(?:y|iness)\b",
        r"\b(?:no ?one|nobody)\s+(?:talks|speaks|comes|visits)\b",
    )
)
_LONELY_FOLDED = tuple(fold(p) for p in LONELY_PHRASES)


def is_lonely(text: str) -> bool:
    folded = fold(text)
    return has_any(folded, _LONELY_FOLDED) or any(p.search(folded) for p in _LONELY_PATTERNS)


# ---- Health complaints that are NOT an emergency (task C, boundary 5) --------------------------------------------
# "डोकं दुखतं", "ताप आलाय", "झोप येत नाही", "मी काल पडले होते". Arjun gives NO advice: a fixed warm reply, a family note
# (only with the family-alert consent) and the conversation goes on. Checked AFTER emergency / distress, and only when
# the turn is not an explicit care command. UNVERIFIED lexicon, same status as the three above: written without a
# native speaker or real Prisma output, so it must be reviewed before any public demo. Patterns are written in natural
# spelling and folded by _pat (ि -> ी, ु -> ू, ँ -> ं), because they run on fold()ed text.
def _pat(text: str) -> re.Pattern[str]:
    return re.compile(unicodedata.normalize("NFC", text).translate(_DROP).translate(_FOLD))


_PAIN = r"(?:दुख|दुःख|ठणक|ठसठस|कळ)\S*(?!\S)(?!\s+(?:नाही|नहीं|नही))"  # hurts / throbs / aches
_SYMPTOM_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "head": tuple(
        _pat(p)
        for p in (
            rf"(?<!\S)डोक\S*\s+(?:\S+\s+)?{_PAIN}",
            r"(?<!\S)डोकेदुख\S*",
            r"(?<!\S)(?:सिर|सर)\s+(?:में\s+)?(?:दर्द|दुख)\S*",
            r"(?<!\S)सिरदर्द\S*",
            r"\bheadache\b|\bhead\s+(?:hurts|aches|is\s+paining|is\s+aching)\b",
            r"\bdoka\s+(?:\w+\s+)?dukh\w*|\bsir\s*dard\b",
        )
    ),
    "stomach": tuple(
        _pat(p)
        for p in (
            rf"(?<!\S)पोट(?:ात)?\s+(?:\S+\s+)?{_PAIN}",
            r"(?<!\S)पेट\s+(?:में\s+)?(?:दर्द|दुख)\S*",
            r"\bstomach\s?ache\b|\btummy\s?ache\b|\bstomach\s+(?:pain|hurts)\b",
            r"\bpot(?:at)?\s+(?:\w+\s+)?dukh\w*",
        )
    ),
    "fever": tuple(
        _pat(p)
        for p in (
            r"(?<!\S)ताप\s+(?:आ\S*|आहे|येत\S*)",
            r"(?<!\S)बुखार\S*",
            r"\bfever\b",
            r"\btaap\s+(?:aal\w*|aahe|yet\w*)",
        )
    ),
    "joint": tuple(
        _pat(p)
        for p in (
            rf"(?<!\S)(?:गुडघ\S*|कंबर|पाठ|पाठी\S*|पाय|पायात|मान|खांद\S*|कोपर|हात)\s+(?:\S+\s+)?{_PAIN}",
            r"(?<!\S)(?:गुडघे|कंबर|पाठ)दुख\S*",
            r"(?<!\S)(?:घुटन\S*|कमर|पीठ|कंधे|कंधा|पैर|टांग)\s+(?:में\s+)?(?:दर्द|दुख)\S*",
            r"\b(?:knees?|back|legs?|shoulders?|neck|joints?)\s+(?:hurts?|aches?|is\s+paining|are\s+paining)\b",
            r"\b(?:knee|back|joint|leg)\s+pain\b|\bbackache\b",
            r"\bgudgh\w*\s+(?:\w+\s+)?dukh\w*|\bkambar\s+(?:\w+\s+)?dukh\w*",
        )
    ),
    "sleep": tuple(
        _pat(p)
        for p in (
            r"(?<!\S)झोप\s+(?:\S+\s+)?(?:येत|लागत)\S*\s+नाही",
            r"(?<!\S)नींद\s+(?:\S+\s+)?(?:नहीं|नही)",
            r"\bcan.?t\s+sleep\b|\bsleepless\b|\bno\s+sleep\b",
            r"\bjhop\s+(?:\w+\s+)?nahi\b",
        )
    ),
    "fall_past": tuple(
        _pat(p)
        for p in (
            r"(?<!\S)(?:मी\s+)?पडल(?:े|ो|ी)\s+होत\S*",
            r"(?<!\S)(?:मैं\s+)?गिर\s+ग(?:या|ई|यी)\s+थ\S*",
            r"\bmi\s+padl(?:e|o|i)\s+hot\w*",
        )
    ),
    "unwell": tuple(
        _pat(p)
        for p in (
            r"(?<!\S)बरं\s+(?:\S+\s+)?वाटत\S*\s+नाही",
            r"(?<!\S)बरं\s+नाही\s+वाटत\S*",
            r"(?<!\S)बरे\s+वाटत\S*\s+नाही",
            r"(?<!\S)तब्येत\s+(?:\S+\s+)?(?:ठीक|बरी|चांगली)\s+नाही",
            r"(?<!\S)तबीयत\s+(?:ठीक\s+नहीं|ठीक\s+नही|खराब)",
            r"(?<!\S)(?:मळमळ|उलटी|उल्टी|खोकला|खांसी|अशक्तपणा|कमजोरी)\S*",
            r"(?<!\S)सर्दी\s+(?:झाली|झालीय|झालीये|आहे)\S*",
            r"(?<!\S)डोक\S*\s+जड\S*",
            r"\bcough(?:ing)?\b",
            r"\bnot\s+feeling\s+well\b|\bfeel(?:ing)?\s+(?:sick|unwell|weak|nauseous)\b|\bnausea\b",
            r"\bbara\s+vatat\s+nahi\b",
        )
    ),
}
# A childhood story about falling is a memory, not a complaint.
_PAST_STORY = _pat(
    r"(?<!\S)(?:लहानपणी|लहानपण|बालपणी|बचपन|childhood|as\s+a\s+child|when\s+i\s+was\s+(?:small|young|little))(?!\S)"
)


def symptom_category(text: str) -> str | None:
    """The kind of health complaint in this turn ("head", "stomach", "fever", "joint", "sleep", "fall_past",
    "unwell"), or None. Never a diagnosis: only the words she said, grouped. Run AFTER is_emergency / is_distress."""
    folded = fold(text)
    for category, patterns in _SYMPTOM_PATTERNS.items():
        if category == "fall_past" and _PAST_STORY.search(folded):
            continue
        if any(p.search(folded) for p in patterns):
            return category
    return None
