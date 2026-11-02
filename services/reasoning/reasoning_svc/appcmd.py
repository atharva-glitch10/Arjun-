"""Voice commands for apps: YouTube, news, WhatsApp, family-approved links, and "stop / next / volume" while a
video plays. Rules only (Marathi / Hindi / English). UNVERIFIED lexicon: written without a native speaker or real
Prisma output, like the safety lexicons; review before any public demo.

This module only READS words. What gets opened comes from the family's app_links (core-api) and is chosen in
turn.py; nothing here, and nothing the LLM says, can produce a URL.
"""

import re
from dataclasses import dataclass

from .textutil import normalize, tokens

OPEN_MEDIA = "OPEN_MEDIA"
NEWS_READ = "NEWS_READ"
OPEN_WHATSAPP = "OPEN_WHATSAPP"
OPEN_LINK = "OPEN_LINK"
MEDIA_CONTROL = "MEDIA_CONTROL"
APP_INTENTS = frozenset({OPEN_MEDIA, NEWS_READ, OPEN_WHATSAPP, OPEN_LINK, MEDIA_CONTROL})
CONTROLS = ("stop", "pause", "resume", "next", "volume_up", "volume_down")

_YOUTUBE = re.compile(r"(?:यू|यु)\s?ट्य[ूु]ब|you\s?tube")
_WHATSAPP = re.compile(r"व्?ह?[ाॉॅ]ट्?स\s?[अआएऐॲऍ][ॅ्]?[ं]?\s?[पप]|वाट्सऐप|whats\s?app|watsapp")

# words that are never part of a song / singer / name
_FILLER = frozenset(
    "मला मी आहे आहेत आहेस ना जरा आता तू तुम्ही अर्जुन arjun please वर ते ती एक एखादं एखादे काहीतरी काही "
    "की आणि पण mujhe मुझे ek एक zara जरा abhi अभी kar कर kara करा karo करो de दे dya द्या".split()
)
_PLAY_EXACT = frozenset(
    "लाव लावा लावू लावतोस लावशील लावाल लावून लगा लगाओ लगाइए लगाना चलाओ चला चलाइए चलाना play chalao laga lagao lav lava "
    "सुरू सुरु चालू सुनाओ सुनाइए सुनना देखना दिखाओ listen watch दाखव दाखवा".split()
)
_PLAY_STEMS = ("ऐकव", "ऐकाय", "ऐकूया", "बघाय", "पाहाय", "पहाय", "पाहूया", "बघूया", "सुनाय", "देखन", "सुनन")
_MEDIA_NOUN_STEMS = (
    "गाण", "भजन", "अभंग", "कीर्तन", "गीत", "संगीत", "लावणी", "पोवाड", "आरती", "गझल", "ग़ज़ल", "भक्तिगीत", "स्तोत्र",
    "song", "music", "bhajan", "gaan", "gana", "geet", "ghazal", "aarti", "gaane", "kirtan",
)
_NEWS_NOUNS = ("बातम्या", "बातमी", "बातम्यां", "न्यूज", "न्यूझ", "न्यूज़", "समाचार", "खबर", "खबरें", "खबरे", "ख़बर", "ख़बरें",
               "news", "headlines", "headline", "ताज्या")
_NEWS_WATCH_STEMS = ("बघ", "पाह", "पहा", "पहाय", "लाव", "दाखव", "देखन", "देखो", "दिखा", "चॅनल", "चैनल", "लाईव्ह", "लाइव", "टीव्ही", "टीवी")
_NEWS_WATCH_EXACT = frozenset({"channel", "live", "watch", "tv", "play", "चलाओ", "लगाओ"})
_NEWS_READ_STEMS = ("ऐकव", "ऐकाय", "सांग", "वाच", "सुना", "सुनो", "सुनन", "ऐकू")
_NEWS_READ_EXACT = frozenset({"read", "tell", "headlines", "headline"})
_LINK_VERB_STEMS = ("दाखव", "उघड", "खोल", "दिखा", "दिखाओ", "बघाय", "बघा")
_LINK_VERB_EXACT = frozenset({"open", "show", "दाखव", "दाखवा"})

_STOP_WORDS = frozenset("थांबव थांबवा बंद stop band रोक रोको रोकिए बंद-कर".split())
_CONTROL_NOISE = frozenset("अर्जुन arjun जरा आता please ना कर करा karo kar कृपया तू".split())
_DOWN = frozenset("कमी हळू कम धीमा धीरे low down lower खाली कमि".split())
_UP = frozenset("वाढव वाढवा जास्त मोठा मोठी मोठं बढ़ा बढ़ाओ बढाओ ज्यादा up high louder loud higher".split())
_NEXT = frozenset("पुढचं पुढचे पुढचा पुढची पुढचंच अगला अगली अगले next agla skip".split())
_PAUSE = frozenset("pause पॉज पॉझ".split())
_RESUME = frozenset("सुरू सुरु चालू resume continue".split())
_MAX_CONTROL_WORDS = 6


@dataclass
class AppCmd:
    intent: str
    control: str | None = None  # MEDIA_CONTROL: stop | pause | resume | next | volume_up | volume_down
    topic: str | None = None  # OPEN_MEDIA: "news_live" | "play" | "youtube"
    query: str = ""  # the words left after the command words: a song / singer / name / link label


def _is(tok: str, exact: frozenset[str], stems: tuple[str, ...] = ()) -> bool:
    return tok in exact or any(tok.startswith(s) for s in stems)


def _has(toks: list[str], exact: frozenset[str], stems: tuple[str, ...] = ()) -> bool:
    return any(_is(t, exact, stems) for t in toks)


def media_noun(tok: str) -> bool:
    return any(tok.startswith(s) for s in _MEDIA_NOUN_STEMS)


def _control(toks: list[str]) -> str | None:
    """stop / pause / resume / next / volume, said as a short phrase ("अर्जुन, थांबव", "आवाज कमी कर")."""
    words = [t for t in toks if t not in _CONTROL_NOISE]
    if not words or len(words) > _MAX_CONTROL_WORDS:
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

    control = _control(toks)
    if control is not None:
        return AppCmd(MEDIA_CONTROL, control=control)

    if _WHATSAPP.search(norm):
        query = " ".join(t for t in toks if not _WHATSAPP.search(t) and t not in _FILLER
                         and t not in _PLAY_EXACT and t not in {"कॉल", "call", "फोन", "वर", "मेसेज", "message", "msg", "उघड", "उघडा"})
        return AppCmd(OPEN_WHATSAPP, query=query)

    news = _has(toks, frozenset(_NEWS_NOUNS))
    if news:
        watch = _has(toks, _NEWS_WATCH_EXACT, _NEWS_WATCH_STEMS)
        read = _has(toks, _NEWS_READ_EXACT, _NEWS_READ_STEMS)
        if watch and not (read and _has(toks, frozenset(), ("ऐकव", "ऐकाय", "सांग", "वाच"))):
            return AppCmd(OPEN_MEDIA, topic="news_live")
        if read or len(toks) <= 3:
            return AppCmd(NEWS_READ)
        return None  # "आज बातम्यांमध्ये काय आलं ते मला कळलं नाही": talk, not a command

    youtube = bool(_YOUTUBE.search(norm))
    play = _has(toks, _PLAY_EXACT, _PLAY_STEMS)
    noun = any(media_noun(t) for t in toks)
    if youtube or (play and noun):
        words = [t for t in toks if not _YOUTUBE.search(t) and t not in _FILLER and not _is(t, _PLAY_EXACT, _PLAY_STEMS)
                 and t not in {"बघायचं", "बघायचे", "बघायची", "उघड", "उघडा", "open"}]
        generic = all(media_noun(t) for t in words)
        return AppCmd(OPEN_MEDIA, topic="youtube" if youtube and not words else "play", query="" if generic else " ".join(words))

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
