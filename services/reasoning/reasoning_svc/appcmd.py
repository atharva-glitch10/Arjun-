"""Voice commands for apps: YouTube, news, WhatsApp, family-approved links, and "stop / next / volume" while a
video plays. Rules only (Marathi / Hindi / English). UNVERIFIED lexicon: written without a native speaker or real
Prisma output, like the safety lexicons; review before any public demo.

This module only READS words. What gets opened comes from the family's app_links (core-api) and is chosen in
turn.py; nothing here, and nothing the LLM says, can produce a URL.
"""

import re
from dataclasses import dataclass

from .apps import detect_app
from .textutil import has_any, normalize, tokens

OPEN_MEDIA = "OPEN_MEDIA"
NEWS_READ = "NEWS_READ"
OPEN_WHATSAPP = "OPEN_WHATSAPP"
OPEN_LINK = "OPEN_LINK"
OPEN_APP = "OPEN_APP"
MEDIA_CONTROL = "MEDIA_CONTROL"
APP_INTENTS = frozenset({OPEN_MEDIA, NEWS_READ, OPEN_WHATSAPP, OPEN_LINK, OPEN_APP, MEDIA_CONTROL})
CONTROLS = ("stop", "pause", "resume", "next", "volume_up", "volume_down")

_YOUTUBE = re.compile(r"(?:यू|यु)\s?ट्य[ूु]ब|you\s?tube")
_WHATSAPP = re.compile(r"व्?ह?[ाॉॅ]ट्?स\s?[अआएऐॲऍ][ॅ्]?[ं]?\s?[पप]|वाट्सऐप|whats\s?app|watsapp")

# UNVERIFIED lexicon (no native-speaker review): these word lists were written from the user stories and need a
# native speaker / real speech before a public demo.
# words that are never part of a song / singer / name
_FILLER = frozenset(
    "मला मी आहे आहेत आहेस ना जरा आता तू तुम्ही अर्जुन arjun please वर मध्ये ते ती एक एखादं एखादे काहीतरी काही "
    "की आणि पण mujhe मुझे ek एक zara जरा abhi अभी kar कर kara करा karo करो de दे dya द्या "
    "नाही नहीं nahi nahin नको nako".split()
)
# The request itself is never part of the search: "बघायचं" / "उघड" / "व्हिडिओ" are how she asks, not what she wants.
_QUERY_DROP = _FILLER | frozenset(
    "बघायचं बघायचा बघायची बघायचे ऐकायचं ऐकायचा ऐकायची ऐकायचे उघड उघडा open show please "
    "व्हिडिओ व्हिडीओ व्हिडीयो video vidio लिंक link".split()
)
# Marathi possessives: "जोशींचं" -> "जोशी", "मंगेशकरचं/ची/चां" -> "मंगेशकर", "विठ्ठलाची" -> "विठ्ठल".
# Longest first so "मंगेशकरांनी" never loses only the last two letters.
_POSSESSIVE = (
    "ांचं", "ांची", "ांचा", "ांचे",
    "ाचं", "ाची", "ाचा", "ाचे",
    "ंचं", "ंची", "ंचा", "ंचे",
    "चं", "ची", "चा", "चे",
    "ला", "ने",
)
_PLAY_EXACT = frozenset(
    "लाव लावा लावू लावतोस लावशील लावाल लावून लगा लगाओ लगाइए लगाना चलाओ चला चलाइए चलाना play chalao laga lagao lav lava "
    "सुरू सुरु चालू सुनाओ सुनाइए सुनना देखना दिखाओ listen watch दाखव दाखवा उघड उघडा open show दे द्या देना sunao dikhao"
    .split()
)
_PLAY_STEMS = ("ऐकव", "ऐकाय", "ऐकूया", "बघाय", "पाहाय", "पहाय", "पाहूया", "बघूया", "सुनाय", "देखन", "सुनन")
_MEDIA_NOUN_STEMS = (
    "गाण", "भजन", "अभंग", "कीर्तन", "गीत", "संगीत", "लावणी", "पोवाड", "आरती", "गझल", "ग़ज़ल", "भक्तिगीत", "स्तोत्र",
    "song", "music", "bhajan", "gaan", "gana", "geet", "ghazal", "aarti", "gaane", "kirtan",
    # a video / a video link is a media pointer, never part of a search query
    "व्हिडिओ", "व्हिडीओ", "व्हिडीयो", "video", "vidio",
)
# "यूट्यूबची लिंक दे" / "video link": a pointer, not a song name (clean_query drops these too)
_NEWS_NOUNS = ("बातम्या", "बातमी", "बातम्यां", "न्यूज", "न्यूझ", "न्यूज़", "समाचार", "खबर", "खबरें", "खबरे", "ख़बर", "ख़बरें",
               "news", "headlines", "headline", "ताज्या")
_NEWS_WATCH_STEMS = ("बघ", "पाह", "पहा", "पहाय", "लाव", "दाखव", "देखन", "देखो", "दिखा", "चॅनल", "चैनल", "लाईव्ह", "लाइव", "टीव्ही", "टीवी")
_NEWS_WATCH_EXACT = frozenset({"channel", "live", "watch", "tv", "play", "चलाओ", "लगाओ"})
_NEWS_READ_STEMS = ("ऐकव", "ऐकाय", "सांग", "वाच", "सुना", "सुनो", "सुनन", "ऐकू")
_NEWS_READ_EXACT = frozenset({"read", "tell", "headlines", "headline"})
_LINK_VERB_STEMS = ("दाखव", "उघड", "खोल", "दिखा", "दिखाओ", "बघाय", "बघा")
_LINK_VERB_EXACT = frozenset({"open", "show", "दाखव", "दाखवा"})

# ---- what a media request is ABOUT (recipe / exercise / a video, not only YouTube + play) ---------------------
# The old parser needed a play verb plus a song word. These shapes also catch "मला मिठाई बनवायची आहे" and
# "पुरणपोळी कशी करतात", which used to fall through to the companion LLM. UNVERIFIED lexicon.
_MEDIA_WORD_STEMS = (
    "गाण", "गीत", "संगीत", "भजन", "अभंग", "आरती", "कीर्तन", "भक्तिगीत", "स्तोत्र", "लावणी", "पोवाड", "गझल",
    "बातम", "न्यूज", "न्यूझ", "न्यूज़", "समाचार", "खबर", "ख़बर",
    "व्यायाम", "योग", "रेसिपी", "पाककृती", "व्हिडिओ", "व्हिडीओ", "व्हिडीयो",
    "song", "music", "bhajan", "gaan", "gana", "geet", "ghazal", "aarti", "gaane", "kirtan",
    "news", "recipe", "exercise", "yoga", "video", "vidio",
)
_RECIPE_PHRASES = (
    "कसं करतात", "कशी करतात", "कसे करतात", "कसा करतात", "कसं बनवतात", "कशी बनवतात", "कसे बनवतात",
    "कसं बनवायचं", "कशी बनवायची", "कसे बनवायचे", "कसा बनवायचा",
    "बनवायची आहे", "बनवायचं आहे", "बनवायचे आहे", "बनवायचा आहे",
    "how to make", "recipe", "रेसिपी", "पाककृती",
)
# Words that name the REQUEST, not the thing to search for.
_MEDIA_TOPIC_DROP = frozenset(
    "आहे आहेत आहेस आणि कशी कसा कसं कसे करतात करतो करते करायचं करायची करायचा बनवायची बनवायचं बनवायचे "
    "बनवायचा बनवतात सांग सांगा शिकव शिकवा".split()
)
# A category word is not a "specific" request; a singer / dish / programme name is.
_GENERIC_MEDIA = frozenset(
    "गाणं गाणी गीत गीतं संगीत भजन भजनं अभंग आरती कीर्तन बातम्या बातमी न्यूज न्यूझ समाचार खबर खबरें "
    "व्यायाम योग रेसिपी पाककृती मिठाई मराठी जुनी जुने चांगलं चांगली चांगले काही काहीतरी "
    "video song songs music news recipe exercise yoga".split()
)

_STOP_WORDS = frozenset("थांब थांबव थांबवा बंद stop band रोक रोको रोकिए बंद-कर परत".split())
_CONTROL_NOISE = frozenset("अर्जुन arjun जरा आता please ना कर करा karo kar कृपया तू".split())
_DOWN = frozenset("कमी हळू कम धीमा धीरे low down lower खाली कमि".split())
_UP = frozenset("वाढव वाढवा जास्त मोठा मोठी मोठं बढ़ा बढ़ाओ बढाओ ज्यादा up high louder loud higher".split())
_NEXT = frozenset("पुढचं पुढचे पुढचा पुढची पुढचंच अगला अगली अगले next agla skip".split())
_PREVIOUS = frozenset("मागचं मागचा मागची मागचे मागे previous पिछला पिछली पीछे back".split())
_PAUSE = frozenset("pause पॉज पॉझ".split())
_RESUME = frozenset("सुरू सुरु चालू resume continue".split())
# A control is only a control in a short phrase, or when it is addressed to Arjun ("अर्जुन, ...").
_MAX_CONTROL_WORDS = 4
_WAKE_NAMES = ("अर्जुन", "arjun")


@dataclass
class AppCmd:
    intent: str
    control: str | None = None  # MEDIA_CONTROL: stop | pause | resume | next | previous | volume_up | volume_down
    topic: str | None = None  # OPEN_MEDIA: "news_video" | "youtube" | "play"
    query: str = ""  # the words left after the command words: a song / singer / name / link label


def _is(tok: str, exact: frozenset[str], stems: tuple[str, ...] = ()) -> bool:
    return tok in exact or any(tok.startswith(s) for s in stems)


def _has(toks: list[str], exact: frozenset[str], stems: tuple[str, ...] = ()) -> bool:
    return any(_is(t, exact, stems) for t in toks)


def media_noun(tok: str) -> bool:
    return any(tok.startswith(s) for s in _MEDIA_NOUN_STEMS)


def _strip_possessive(tok: str) -> str:
    """A name without its Marathi possessive ending ("जोशींचं" -> "जोशी"). Content words are left alone:
    "गाणं" / "आरती" / "भजन" do not end in one of these suffixes after a real stem."""
    for suffix in _POSSESSIVE:
        if tok.endswith(suffix) and len(tok) - len(suffix) >= 2:
            return tok[: -len(suffix)]
    return tok


def clean_query(text: str) -> str:
    """The words worth searching for: request/filler words and YouTube/play words removed, name possessives stripped.
    "भीमसेन जोशींचं भजन लावा" -> "भीमसेन जोशी भजन"; "यूट्यूबवर पु ल देशपांडे दाखव" -> "पु ल देशपांडे"."""
    out = []
    for tok in tokens(normalize(text)):
        if not tok or _YOUTUBE.search(tok) or _is(tok, _PLAY_EXACT, _PLAY_STEMS):
            continue
        tok = _strip_possessive(tok)
        if tok and tok not in _QUERY_DROP:
            out.append(tok)
    return " ".join(out)


def media_topic(text: str) -> str:
    """The search words of a media request: the request/question words dropped, the thing kept.
    "मला मिठाई बनवायची आहे" -> "मिठाई"; "पुरणपोळी कशी करतात" -> "पुरणपोळी"."""
    return " ".join(t for t in tokens(clean_query(text)) if t not in _MEDIA_TOPIC_DROP)


def media_kind(text: str) -> str:
    """The kind of media this request is about (rules fallback for the Sarvam understanding)."""
    norm = normalize(text)
    toks = tokens(norm)
    topic = media_topic(text)
    if _has(toks, frozenset(_NEWS_NOUNS)):
        return "news"
    if has_any(norm, _RECIPE_PHRASES) or any(t.startswith(("रेसिप", "पाककृती")) for t in toks):
        return "recipe"
    if any(t.startswith(("भजन", "अभंग", "आरती", "कीर्तन", "भक्तिगीत", "स्तोत्र"))
           or t in ("bhajan", "aarti", "kirtan") for t in toks):
        return "devotional"
    if any(t.startswith(("गाण", "गीत", "संगीत", "गझल", "लावणी", "पोवाड"))
           or t in ("song", "music", "gaan", "gana", "geet", "ghazal", "gaane") for t in toks):
        return "music"
    if any(t.startswith(("व्यायाम", "योग")) or t in ("exercise", "yoga") for t in toks):
        return "exercise"
    if _YOUTUBE.search(norm) or any(t.startswith(("व्हिडिओ", "व्हिडीओ", "व्हिडीयो")) or t in ("video", "vidio")
                                    for t in toks):
        # "यूट्यूब लाव" / "व्हिडिओ दाखव" name no subject: the short question is better than a random video.
        return "video" if topic and not all(t in _GENERIC_MEDIA for t in tokens(topic)) else "unknown"
    return "unknown"


def media_specific(text: str, kind: str | None = None, topic: str | None = None) -> bool:
    """True only when she named a particular singer / song / dish / programme, not a category."""
    kind = kind or media_kind(text)
    topic = media_topic(text) if topic is None else topic
    if not topic or kind == "news":
        return False
    words = [t for t in tokens(topic) if t not in _GENERIC_MEDIA]
    if kind == "recipe":
        return bool(words)  # "मिठाई" is a category; "पुरणपोळी" is a dish
    return bool(words)


def is_media_request(text: str) -> bool:
    """A request to watch / listen to something, not a story that merely mentions a song or YouTube.

    Request-shaped: YouTube / a media word plus a play or show verb, a recipe question ("कसं करतात",
    "बनवायचं"), or exercise + show. "मला गाणं आठवलं..." and "माझ्या नातवाने यूट्यूबवर काम केलं" stay chat.
    """
    norm = normalize(text)
    if not norm:
        return False
    toks = tokens(norm)
    if has_any(norm, _RECIPE_PHRASES):
        # A how-to question is answered conversationally; only an explicit request to watch/play a recipe is media.
        recipe_media = any(t in toks for t in ("व्हिडिओ", "video", "youtube", "यूट्यूब", "दाखव", "लाव", "play"))
        return recipe_media
    media_word = bool(_YOUTUBE.search(norm)) or any(
        t.startswith(_MEDIA_WORD_STEMS) for t in toks
    )
    play = _has(toks, _PLAY_EXACT, _PLAY_STEMS)
    return media_word and play


def _control(toks: list[str]) -> str | None:
    """stop / pause / resume / next / volume, said as a short phrase ("अर्जुन, थांबव", "आवाज कमी कर")."""
    addressed = bool(toks) and toks[0] in _WAKE_NAMES
    if len(toks) > _MAX_CONTROL_WORDS and not addressed:
        return None
    words = [t for t in toks if t not in _CONTROL_NOISE]
    if not words:
        return None
    volume = any(t.startswith("आवाज") or t in ("volume", "awaaz", "awaz") for t in words)
    if volume or any(t in ("louder", "volume") for t in words):
        if _has(words, _DOWN):
            return "volume_down"
        if _has(words, _UP):
            return "volume_up"
        return None
    if _has(words, _NEXT) and not {"what", "what's", "whats", "काय", "क्या", "kay", "kya"} & set(words):
        return "next"
    if _has(words, _PREVIOUS):
        return "previous"
    if _has(words, _STOP_WORDS):
        return "stop"
    if _has(words, _PAUSE):
        return "pause"
    if any(t in _RESUME for t in words) and not any(media_noun(t) for t in words) and len(words) <= 3:
        return "resume"
    return None


def parse_app_command(text: str, *, remind: bool = False, links: bool = False) -> AppCmd | None:
    """The app command in this sentence, or None. A reminder request ("...आठवण करून द्या") is never an app command, and
    a story that merely MENTIONS a song ("मला गाणं आठवलं, लहानपणी आम्ही गायचो") has no command word, so it stays chat."""
    if remind:
        return None
    norm = normalize(text).replace("‍", "").replace("‌", "")  # "व्हॉट्सअ‍ॅप" has a joiner
    if not norm:
        return None
    toks = tokens(norm)

    # A video-call request is handled as a family-call intent by turn.py, never as a YouTube video.
    if any(t.startswith(("व्हिडिओ", "वीडिओ")) or t == "video" for t in toks) and any(
        t in ("कॉल", "call", "मुलाला", "मुलगा", "son", "bolav", "बोलव") for t in toks
    ):
        return None

    control = _control(toks)
    if control is not None:
        return AppCmd(MEDIA_CONTROL, control=control)

    if _WHATSAPP.search(norm):
        query = " ".join(t for t in toks if not _WHATSAPP.search(t) and t not in _FILLER
                         and t not in _PLAY_EXACT and t not in {"कॉल", "call", "फोन", "वर", "मेसेज", "message", "msg", "उघड", "उघडा"})
        return AppCmd(OPEN_WHATSAPP, query=query)

    # A phone app she names ("स्पॉटिफायवर भजन लाव", "मॅप्स उघड"): checked before YouTube so "यूट्यूब म्युझिक" is the app.
    # Like YouTube, naming the app is not enough ("नातू स्पॉटिफाय वापरतो"): she must ask to play / open / show.
    named = detect_app(norm)
    if named is not None and (_has(toks, _PLAY_EXACT, _PLAY_STEMS) or _has(toks, _LINK_VERB_EXACT, _LINK_VERB_STEMS)):
        app_id, name = named
        rest = norm.replace(name, " ")
        words = [t for t in tokens(clean_query(rest)) if t not in ("वर", "मध्ये", "मधे", "पर", "on", "in")]
        words = [t for t in words if not any(t.startswith(p) for p in ("मध्ये", "वर"))]
        return AppCmd(OPEN_APP, topic=app_id, query=" ".join(words)[:100])

    news = _has(toks, frozenset(_NEWS_NOUNS))
    if news:
        watch = _has(toks, _NEWS_WATCH_EXACT, _NEWS_WATCH_STEMS)
        read = _has(toks, _NEWS_READ_EXACT, _NEWS_READ_STEMS)
        if watch and not (read and _has(toks, frozenset(), ("ऐकव", "ऐकाय", "सांग", "वाच"))):
            return AppCmd(OPEN_MEDIA, topic="news_video")
        if read or len(toks) <= 3:
            return AppCmd(NEWS_READ)
        return None  # "आज बातम्यांमध्ये काय आलं ते मला कळलं नाही": talk, not a command

    youtube = bool(_YOUTUBE.search(norm))
    play = _has(toks, _PLAY_EXACT, _PLAY_STEMS)
    noun = any(media_noun(t) for t in toks)
    # A mention of YouTube is not a command on its own ("माझ्या नातवाने यूट्यूबवर काम केलं"): she must also ask
    # to play / see / open something, or name a song. This is what keeps stories out of the app commands.
    if (youtube and play) or (play and noun):
        words = clean_query(" ".join(toks))
        generic = not words or all(media_noun(t) for t in tokens(words))
        return AppCmd(OPEN_MEDIA, topic="youtube" if youtube else "play", query="" if generic else words)

    # A recipe question ("पुरणपोळी कशी करतात") or a media word plus a show/play verb ("व्यायाम दाखव") is a media
    # request even without the old song-word + play pair. UNVERIFIED lexicon; stories still stay chat.
    if is_media_request(text):
        return AppCmd(OPEN_MEDIA, topic="youtube", query=media_topic(text))

    link_verb = links and _has(toks, _LINK_VERB_EXACT, _LINK_VERB_STEMS)  # generic "show ...": only as the LAST rule
    if link_verb:
        words = [t for t in toks if t not in _FILLER and not _is(t, _LINK_VERB_EXACT, _LINK_VERB_STEMS)]
        if words:
            return AppCmd(OPEN_LINK, query=" ".join(words))
    return None


# ---- matching a spoken name against the family's labels / names -------------------------------------------------
def _common_prefix(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b, strict=False):
        if x != y:
            break
        n += 1
    return n


def _token_matches(name_tok: str, said_tok: str) -> bool:
    """Equal, or the same stem with a Marathi/Hindi ending ("चंद्रकांतला" ~ "चंद्रकांत", "नातवाचे" ~ "नातवाचे")."""
    if name_tok == said_tok:
        return True
    short = min(len(name_tok), len(said_tok))
    return short >= 3 and _common_prefix(name_tok, said_tok) >= max(3, short - 2)


def name_matches(name: str, text: str) -> bool:
    """Every word of `name` appears (with any ending) in what she said."""
    name_toks = [t for t in tokens(normalize(name)) if t]
    said = tokens(normalize(text))
    return bool(name_toks) and all(any(_token_matches(n, s) for s in said) for n in name_toks)


def covers(names: list[str], query: str) -> bool:
    """Every word of `query` is (a form of) a word of one of the `names`: "भजन" covers "भजन", not "भीमसेन जोशींचं भजन"."""
    pool = [t for n in names for t in tokens(normalize(n))]
    return all(any(_token_matches(n, q) for n in pool) for q in tokens(normalize(query)))
