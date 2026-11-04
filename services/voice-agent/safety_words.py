"""Safety words the voice agent keeps locally so media mode never needs a service to protect her.

GENERATED FILE - DO NOT EDIT. Source of truth: services/reasoning/reasoning_svc/distress.py.
Regenerate with `python scripts/gen_safety_words.py`; test_safety_words_sync.py fails when this file is stale.

No imports from other services (they share contracts, not code), so it works with reasoning and core-api down.
Deliberately recall-biased: a false positive only passes a sentence on to reasoning.
"""

import re
import unicodedata

EMERGENCY_PHRASES: tuple[str, ...] = (
    'chest pain',
    'my chest hurts',
    'pain in my chest',
    "can't breathe",
    'cannot breathe',
    'cant breathe',
    "i can't breathe",
    'unable to breathe',
    'i have fallen',
    'i fell down',
    "can't get up",
    'cannot get up',
    'heart attack',
    'stroke',
    'i am bleeding',
    "i'm bleeding",
    'i fainted',
    'i am fainting',
    'call ambulance',
    'ambulance',
    'i feel dizzy',
    'i am dizzy',
    'feeling dizzy',
    'छातीत दुखतंय',
    'छातीत दुखत आहे',
    'छातीत दुखते',
    'छातीत कळ',
    'श्वास घेता येत नाही',
    'श्वास लागतोय',
    'दम लागतोय',
    'दम लागला',
    'उठता येत नाही',
    'चक्कर येतेय',
    'चक्कर येत आहे',
    'बेशुद्ध',
    'रक्त येतंय',
    'खूप रक्त',
    'हृदयविकार',
    'रुग्णवाहिका',
    'चक्कर आली',
    'चक्कर आले',
    'चक्कर आल्यासारखं',
    'चक्कर येते',
    'चक्कर आ रही',
    'chhatit dukhtay',
    'chatit dukhtay',
    'chhatit dukhat aahe',
    'shwas gheta yet nahi',
    'swas gheta yet nahi',
    'dam lagtoy',
    'uthta yet nahi',
    'chakkar yetey',
    'chakkar yet aahe',
    'rakta yetay',
    'khup rakta',
    'chakkar aali',
    'chakkar yete',
    'सीने में दर्द',
    'छाती में दर्द',
    'सांस नहीं ले पा',
    'साँस नहीं ले पा',
    'सांस नहीं आ रही',
    'उठ नहीं पा',
    'चक्कर आ रहा',
    'बेहोश',
    'खून बह रहा',
    'seene mein dard',
    'seene me dard',
    'chhati mein dard',
    'saans nahi le pa',
    'sans nahi aa rahi',
    'uth nahi pa',
    'chakkar aa raha',
    'behosh',
    'khoon beh raha',
)

DISTRESS_PHRASES: tuple[str, ...] = (
    'kill myself',
    'want to die',
    'wanna die',
    'end my life',
    'no reason to live',
    'nothing to live for',
    'hopeless',
    'i give up',
    'better off dead',
    'hurt myself',
    'suicide',
    'someone is hurting me',
    'he hits me',
    'she hits me',
    'they hit me',
    'i am afraid',
    'i am scared',
    "i'm scared",
    "i'm afraid",
    'nobody cares',
    'मरना चाहता हूँ',
    'मरना चाहती हूँ',
    'जीने का मन नहीं',
    'जीने की इच्छा नहीं',
    'आत्महत्या',
    'मुझे डर लग रहा है',
    'मुझे मारते हैं',
    'कोई मुझे मारता है',
    'सब खत्म',
    'marna chahta hoon',
    'marna chahti hoon',
    'jeene ka mann nahi',
    'mujhe dar lag raha hai',
    'mujhe maarte hain',
    'koi mujhe maarta hai',
    'sab khatam',
    'मला मरायचं आहे',
    'मला मरावंसं वाटतं',
    'जगायची इच्छा नाही',
    'जगावंसं वाटत नाही',
    'आत्महत्या करावी',
    'मला भीती वाटतेय',
    'मला भीती वाटते',
    'मला कोणी मारतं',
    'मला कुणी मारतं',
    'सगळं संपलं',
    'सगळं संपवावं',
    'mala marayche aahe',
    'mala marayacha aahe',
    'mala maravasa vatta',
    'jagaychi iccha nahi',
    'jagavasa vatat nahi',
    'mala bhiti vatte',
    'mala bhiti vatate',
    'mala koni marto',
    'mala koni marte',
    'mala kuni marto',
    'sagla sampla',
    'sagla sampavave',
)

_EMERGENCY_PATTERNS: tuple[str, ...] = (
    '(?<!\\S)(?:मी\\s+)?पडल(?:े|ो|ी)(?:\\s+आहे)?(?!\\s*(?:होत|होतं))(?:\\s|$)',
    '\\bmi\\s+padl(?:e|o|i)\\b(?!\\s+hot)',
    '(?<!\\S)(?:मैं\\s+)?गीर\\s+ग(?:या|ई|यी)(?!\\s+था|\\s+थी)',
    '\\b(?:main\\s+)?gir\\s+ga(?:ya|yi|i)\\b(?!\\s+th)',
    '\\bi\\s+(?:just\\s+)?fell\\b',
)

_DISTRESS_PATTERNS: tuple[str, ...] = (
    '(?<!\\S)मरा(?:यच|वंस|वेस)\\S*',
    '(?<!\\S)जगा(?:यच|यला|वंस|वेस)\\S*(?:\\s+\\S+){0,2}\\s+(?:नाही|नको)(?!\\S)',
    '(?<!\\S)मर(?:जा)?(?:ना|ने)\\s+चाह\\S*',
    '(?<!\\S)मर\\s+जा(?:ऊं|ऊंगा|ऊंगी|ना\\s+चाह\\S*)',
    '(?<!\\S)जी(?:ना|ने)\\s+(?:का\\s+मन\\s+)?(?:नहीं|नही)(?!\\S)',
    '(?<!\\S)जीवन\\s+(?:खत्म|समाप्त|संपव)\\S*',
    '\\bmaray(?:ch|ach|avas|aves)\\w*',
    '\\bmarun\\s+(?:jain|jau|jaycha|jav)\\w*',
    '\\bmar\\s+jau\\w*',
    '\\bmar(?:na|ne)\\s+chah\\w*',
    '\\bmar\\s+ja+n[ae]\\s+chah\\w*',
    '\\bjag(?:aych|ayach|avas|aves)\\w*\\s+(?:\\w+\\s+){0,2}(?:nahi|nako)\\b',
    '\\bjee?n[ae]\\s+(?:ka\\s+man+\\s+)?nahi\\b',
    '\\bjeevan\\s+sampav\\w*',
    '\\b(?:do not|don.?t)\\s+want\\s+to\\s+(?:live|be\\s+alive|be\\s+here|go\\s+on|exist)\\b',
    '\\bwant\\s+to\\s+(?:end|finish)\\s+(?:it|everything)\\b',
    '\\bend\\s+it\\s+all\\b',
    '\\b(?:can.?t|cannot)\\s+go\\s+on\\b',
    '\\btak(?:e|ing)\\s+my\\s+own\\s+life\\b',
    '\\bno\\s?one\\s+(?:would|will)\\s+miss\\s+me\\b',
    '\\bbetter\\s+off\\s+without\\s+me\\b',
    '\\bwish\\s+i\\s+(?:was|were)\\s+dead\\b',
    '\\bwant\\s+to\\s+disappear\\b',
)

_SPACED_PATTERNS: tuple[str, ...] = (
    '(?<!\\S)(?:attack|atack|atak|अटैक|अैटैक|एटैक)\\s+(?:आला|आलाय|आली|आलं|आलंय|यैतोय|यैतो|यैतैय|यैतै|यैतंय|यैत\\s+आहै|आ\\s+गया|आया|आ\\s+रहा|aala|aalay|yetoy|yete)\\S*',
    '(?<!\\S)(?:हृदय|हार्ट|heart)\\S*\\s+(?:\\S+\\s+)?(?:दूख|दूःख|कळ|pain|hurts?|aches?)\\S*(?!\\s+(?:नाही|नको|नहीं|नही))',
    '(?<!\\S)छाती\\S*\\s+(?:\\S+\\s+)?(?:दूख|दूःख|कळ|दाब|दडपण|जड|आवळ|त्रास|धडधड)\\S*(?!\\s+(?:नाही|नको|नहीं|नही))',
    '\\bchest\\s+(?:\\w+\\s+)?(?:pain|pains|hurts?|aches?|tight|heavy)\\b',
    '\\bpain\\s+in\\s+(?:my\\s+|the\\s+)?chest\\b',
    '\\bchest\\s+(?:\\S+\\s+)?(?:दूख|दूःख|कळ|दाब|जड|त्रास)\\S*',
    '(?<!\\S)(?:bp|बीपी|बी\\s+पी|ब्लड\\s+प्रैशर|blood\\s+pressure|रक्तदाब)\\s+(?:\\S+\\s+){0,3}(?:high|हाय|वाढ\\S*|जास्त|कमी|low|लो|खाली)(?!\\S)(?!\\s+(?:होत))',
    '(?<!\\S)(?:sugar|शूगर)\\s+(?:\\S+\\s+)?(?:low|लो|कमी|खाली|drop\\S*|उतर\\S*)(?!\\S)',
    '(?<!\\S)(?:low|लो)\\s+(?:sugar|शूगर)(?!\\S)',
    '(?<!\\S)(?:stroke|स्ट्रोक|लकवा|लकवै|पक्षाघात|पैरालीसीस|पैरालीसीस|पैरालीसीस|paralysis|paralyzed|paralysed)(?!\\S)',
    '(?<!\\S)तोंड\\s+वाकड\\S*',
    '(?<!\\S)(?:हात|पाय)\\s+(?:लूळा|लूळै|उचलता\\s+यैत\\s+नाही)\\S*',
    '(?<!\\S)बोलता\\s+यैत\\s+नाही',
    '(?<!\\S)(?:faint(?:ed|ing)?|unconscious|blackout|black\\s+out|passed\\s+out|भोवळ\\S*|बैशूद्ध\\S*|बैहोश\\S*)(?!\\S)',
    '(?<!\\S)चक्कर\\s+(?:यैऊन|आऊन|आकर)\\s+(?:\\S+\\s+)?पडल\\S*',
    '(?<!\\S)श्वास\\S*\\s+घैता\\s+यैत\\s+(?:नाही|नही|नहीं)\\S*',
    '(?<!\\S)श्वास\\S*\\s+(?:\\S+\\s+)?(?:घैताना|अडक|कोंड|फूल|लाग|गूदमर|त्रास)\\S*(?!\\s+(?:नाही|नको|नहीं|नही))',
    '(?<!\\S)दम\\s+(?:\\S+\\s+)?(?:लाग|कोंड|घूट|अडक)\\S*(?!\\s+(?:नाही|नको|नहीं|नही))',
    '(?<!\\S)(?:सांस|सांस)\\s+(?:\\S+\\s+)?(?:फूल|फूल|अटक)\\S*',
    '\\b(?:breathless\\w*|short\\s+of\\s+breath|(?:difficulty|trouble|problem|hard)\\s+(?:in\\s+|to\\s+)?breath\\w*|breath\\w*\\s+(?:problem|trouble|difficulty|issue))\\b',
    '(?<!\\S)(?:ब्रीदींग|ब्रीदींग|breathing)\\s+(?:\\S+\\s+)?(?:प्रॉब्लैम|प्रोब्लैम|त्रास|problem|trouble)',
    '(?<!\\S)(?:मी\\s+)?(?:खाली\\s+)?पडल(?:ै|ो|ी)(?:य|यै|ंय)?(?:\\s+आहै)?(?!\\s*(?:होत|होतं))(?:\\s|$)',
    '(?<!\\S)(?:घसरून|तोल\\s+जाऊन|तोल\\s+गैला)\\S*\\s+(?:\\S+\\s+)?पडल\\S*',
    '\\b(?:i\\s+)?(?:have\\s+)?(?:fell|fallen)\\s+(?:down|over)\\b',
    '(?<!\\S)रक्त\\S*\\s+(?:\\S+\\s+)?(?:यैत|पडत|नीघत|वाहत|आल)\\S*(?!\\s+(?:नाही|नको|नहीं|नही))',
    '(?<!\\S)रक्तस्(?:त्)?राव\\S*',
    '\\b(?:bleeding|blood\\s+(?:is\\s+)?(?:coming|flowing|everywhere))\\b',
)

_COMPACT_PATTERNS: tuple[str, ...] = (
    'h(?:ea?|aa?)rtat+a?c?k',
    'हा?र्?ट[अएऐ]ै?ट[ैा]?क',
    'chestpains?',
    'चैस्ट(?:पैन|पैन)',
    'paininmychest|paininthechest',
)

_PAST_MARK_PATTERN = '(?<!\\S)(?:होता|होतं|होते|होती|होतो)(?!\\S)'

_NOW_MARK_PATTERN = '(?<!\\S)(?:येतोय|येतो|येतेय|येते|येतंय|येत|आत्ता|आता|now|right|चाललाय|चाललंय)\\S*'

FAILSAFE_WORDS: tuple[str, ...] = (
    'attack',
    'atak',
    'atack',
    'अटैक',
    'छाती',
    'श्वास',
    'बेशुद्ध',
    'stroke',
    'स्ट्रोक',
    'chest',
)


_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_PUNCT = re.compile(r"[,.?!।;\"“”‘’()\[\]{}]+")
_FOLD = str.maketrans({"ँ": "ं", "ि": "ी", "ु": "ू"})
_DROP = dict.fromkeys([0x200C, 0x200D, 0x093C])  # ZWNJ, ZWJ, nukta
_E_TR = str.maketrans({"ॅ": "ै", "े": "ै", "ॲ": "अ", "ऍ": "अ"})
_TRAILING_HALANT = re.compile("्(?=\\s|$)")


def normalize(text: str) -> str:
    t = _PUNCT.sub(" ", text.lower().translate(_DEVANAGARI_DIGITS))
    return re.sub(r"\s+", " ", t).strip()


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
        parts.append(rf"(?<![a-z0-9]){e}(?![a-z0-9])" if w.isascii() else rf"(?<!\S){e}")
    return re.compile("|".join(parts))


_FAILSAFE_RE = _word_regex(FAILSAFE_WORDS)


def is_distress(text: str) -> bool:
    folded = fold(text)
    return has_any(folded, _DISTRESS_FOLDED) or any(p.search(folded) for p in _DISTRESS_RE)


def loanword_emergency(text: str) -> bool:
    spaced = efold(text)
    compact = re.sub(r"\s+", "", spaced)
    if _PAST_MARK.search(spaced) and not _NOW_MARK.search(spaced):  # a story about the past is not an emergency
        return False
    return any(p.search(spaced) for p in _SPACED_RE) or any(p.search(compact) for p in _COMPACT_RE)


def is_emergency(text: str) -> bool:
    folded = fold(text)
    basic = has_any(folded, _EMERGENCY_FOLDED) or any(p.search(folded) for p in _EMERGENCY_RE)
    return basic or loanword_emergency(text)


def is_safety_phrase(text: str) -> bool:
    return is_emergency(text) or is_distress(text) or bool(_FAILSAFE_RE.search(efold(text)))
