"""Spoken language switch: "मुझसे हिंदी में बात करना", "हिंदीत बोला", "मराठीत बोल", "speak English", "तमिल में बोलो" (2026-11-10).

`parse(text)` finds a request to change the language Arjun speaks. The rules need BOTH a language name (with any ending:
हिंदी / हिंदीत / हिंदीतच / हिंदी में) AND a speaking word (बात, बोल, speak, talk, reply...), and no negation, so "हिंदी सिनेमा लावा"
or "हिंदीत बोलू नको" are not switches. It also says whether she called it permanent ("हमेशा", "नेहमी", "from now on").
The confirmation lines are fixed, in the NEW language, for all ten languages (bn..te UNVERIFIED by a native speaker)."""

from __future__ import annotations

from dataclasses import dataclass

from .textutil import normalize, tokens

# native names: shown / spoken in the confirmation
NAMES: dict[str, str] = {
    "mr": "मराठी", "hi": "हिंदी", "en": "English", "bn": "বাংলা", "gu": "ગુજરાતી", "kn": "ಕನ್ನಡ", "ml": "മലയാളം", "pa": "ਪੰਜਾਬੀ",
    "ta": "தமிழ்", "te": "తెలుగు",
}
# what she may call each language (normalised, prefix-matched so every ending works)
_ALIASES: dict[str, tuple[str, ...]] = {
    "hi": ("हिंदी", "हिन्दी", "हिंदि", "hindi", "hindee"),
    "mr": ("मराठी", "marathi", "marathee"),
    "en": ("इंग्रजी", "अंग्रेजी", "अंग्रेज़ी", "इंग्लिश", "english", "angrezi", "ingraji"),
    "ta": ("तमिल", "तामिळ", "तमिळ", "tamil", "தமிழ்"),
    "te": ("तेलुगू", "तेलगू", "तेलुगु", "telugu", "తెలుగు"),
    "kn": ("कन्नड", "कन्नडा", "kannada", "ಕನ್ನಡ"),
    "ml": ("मल्याळम", "मलयालम", "malayalam", "മലയാളം"),
    "bn": ("बंगाली", "बांग्ला", "bengali", "bangla", "বাংলা"),
    "gu": ("गुजराती", "gujarati", "ગુજરાતી"),
    "pa": ("पंजाबी", "punjabi", "ਪੰਜਾਬੀ"),
}
_SPEAK_PREFIX = ("बोल", "bol", "speak", "talk", "reply", "answer", "respond", "कहो", "सांग", "बताओ")
_SPEAK_EXACT = frozenset({"बात", "बातें", "बातचीत", "जवाब", "उत्तर"})  # exact: "बातम्या" (news) is not "बात"
_NEGATION = frozenset({"नको", "नका", "मत", "नहीं", "नही", "नाही", "not", "dont", "don't", "no", "never", "नये", "नए"})
_PERMANENT = ("हमेशा", "नेहमी", "कायम", "always", "from now on", "आतापासून", "अब से", "आज से", "हर बार", "permanent", "forever", "रोज")


@dataclass(frozen=True)
class Switch:
    lang: str
    permanent: bool


def parse(text: str) -> Switch | None:
    norm = normalize(text)
    toks = tokens(norm)
    if not toks or any(t in _NEGATION for t in toks):
        return None
    if not any(t in _SPEAK_EXACT or t.startswith(_SPEAK_PREFIX) for t in toks):
        return None
    found: str | None = None
    for t in toks:
        for lang, aliases in _ALIASES.items():
            if any(t.startswith(normalize(a)) and len(t) <= len(normalize(a)) + 5 for a in aliases):
                found = lang
        if found:
            break
    if found is None:
        return None
    return Switch(found, any(p in norm for p in _PERMANENT))


def _row(*lines: str) -> dict[str, str]:
    return dict(zip(NAMES, lines, strict=True))


# {lang} is the language's native name. Order: mr hi en bn gu kn ml pa ta te
OK = _row(
    "ठीक आहे, आता मी {lang} भाषेत बोलेन.", "ठीक है, अब मैं {lang} में बात करूंगा।", "Okay, I will speak {lang} now.",
    "ঠিক আছে, এখন আমি {lang}-এ কথা বলব।", "ઠીક છે, હવે હું {lang}માં વાત કરીશ.", "ಸರಿ, ಇನ್ನು ನಾನು {lang}ದಲ್ಲಿ ಮಾತನಾಡುತ್ತೇನೆ.",
    "ശരി, ഇനി ഞാൻ {lang}-ൽ സംസാരിക്കാം.", "ਠੀਕ ਹੈ, ਹੁਣ ਮੈਂ {lang} ਵਿੱਚ ਗੱਲ ਕਰਾਂਗਾ।", "சரி, இனி நான் {lang}-இல் பேசுவேன்.",
    "సరే, ఇకపై నేను {lang}లో మాట్లాడతాను.",
)
KEEP_Q = _row(
    "ही भाषा कायम ठेवू का? हो किंवा नाही सांगा.", "क्या यही भाषा हमेशा रखूँ? हाँ या नहीं बोलिए।", "Shall I always keep this language? Say yes or no.",
    "এই ভাষাটা সবসময় রাখব? হ্যাঁ বা না বলুন।", "આ ભાષા હંમેશ માટે રાખું? હા કે ના કહો.", "ಈ ಭಾಷೆಯನ್ನು ಯಾವಾಗಲೂ ಇಟ್ಟುಕೊಳ್ಳಲೇ? ಹೌದು ಅಥವಾ ಇಲ್ಲ ಎನ್ನಿ.",
    "ഈ ഭാഷ എപ്പോഴും നിലനിർത്തട്ടെ? അതെ അല്ലെങ്കിൽ അല്ല എന്ന് പറയൂ.", "ਕੀ ਇਹ ਭਾਸ਼ਾ ਹਮੇਸ਼ਾ ਰੱਖਾਂ? ਹਾਂ ਜਾਂ ਨਾਂਹ ਕਹੋ।",
    "இந்த மொழியை எப்போதும் வைத்துக்கொள்ளட்டுமா? ஆம் அல்லது இல்லை என்று சொல்லுங்கள்.", "ఈ భాషను ఎప్పుడూ ఉంచనా? అవును లేదా కాదు అని చెప్పండి.",
)
SAVED = _row(
    "ठीक आहे, ही भाषा कायम ठेवतो.", "ठीक है, यही भाषा हमेशा रखूंगा।", "Okay, I will keep this language.", "ঠিক আছে, এই ভাষাই রাখব।",
    "ઠીક છે, આ ભાષા જ રાખીશ.", "ಸರಿ, ಇದೇ ಭಾಷೆಯನ್ನು ಇಟ್ಟುಕೊಳ್ಳುತ್ತೇನೆ.", "ശരി, ഈ ഭാഷ തന്നെ നിലനിർത്താം.", "ਠੀਕ ਹੈ, ਇਹੀ ਭਾਸ਼ਾ ਰੱਖਾਂਗਾ।",
    "சரி, இதே மொழியை வைத்துக்கொள்கிறேன்.", "సరే, ఇదే భాషను ఉంచుతాను.",
)
SESSION_ONLY = _row(
    "ठीक आहे, फक्त आत्तासाठी.", "ठीक है, सिर्फ अभी के लिए।", "Okay, only for now.", "ঠিক আছে, শুধু এখনকার জন্য।", "ઠીક છે, ફક્ત હમણાં માટે.",
    "ಸರಿ, ಈಗಿನ ಮಟ್ಟಿಗೆ ಮಾತ್ರ.", "ശരി, ഇപ്പോഴത്തേക്ക് മാത്രം.", "ਠੀਕ ਹੈ, ਸਿਰਫ਼ ਹੁਣ ਲਈ।", "சரி, இப்போதைக்கு மட்டும்.", "సరే, ప్రస్తుతానికి మాత్రమే.",
)


def confirm(lang: str, permanent: bool) -> str:
    """The one spoken confirmation, in the NEW language: what changed, and (unless she said permanent) one question."""
    head = OK[lang].format(lang=NAMES[lang])
    return f"{head} {SAVED[lang]}" if permanent else f"{head} {KEEP_Q[lang]}"
