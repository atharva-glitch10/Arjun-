"""Turn orchestration. Order is fixed:

  0. physical emergency check (chest pain, breathing, a fall): overrides everything, rules only
  1. distress check (every turn, overrides everything below)
  2. "are you human?" -> AI disclosure
  3. intent: Evon (if configured, schema-validated) -> rule-based fallback
  4. dispatch: care intents are answered from SQL via core-api; the LLM only proposes, core-api
     validates, and anything that writes needs a spoken yes/no.
"""

import json
import logging
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, Callable
from urllib.parse import quote

import httpx

from . import config, replies_langs
from . import replies as rp
from .app_replies import A
from .appcmd import (
    APP_INTENTS,
    CONTROLS,
    MEDIA_CONTROL,
    NEWS_READ,
    OPEN_APP,
    OPEN_LINK,
    OPEN_MEDIA,
    OPEN_WHATSAPP,
    clean_query,
    covers,
    is_media_request,
    media_kind,
    media_specific,
    media_topic,
    name_matches,
    parse_app_command,
)
from .apps import label as app_label
from .checkins import answer_for, topic_of, volunteered_topic
from .clock import local_now
from .core_client import CoreClient, CoreError
from .distress import (
    gives_medical_advice,
    has_failsafe_word,
    has_health_word,
    is_distress,
    is_emergency,
    is_lonely,
    mentions_cardiac,
    symptom_category,
)
from .evon import (
    EvonClient,
    LlmBusy,
    salvage_companion,
    sanitize_companion,
    split_voice_tags,
    strip_filler,
    strip_filler_voiced,
)
from .memory import FactBook, SessionMemory, parse_forget, parse_remember, shape_questions
from .parser import (
    MED_TAKEN_WORDS,
    NO,
    SNOOZE_WORDS,
    STOP,
    YES,
    Draft,
    Parsed,
    Profile,
    apply_text,
    has_med_word,
    parse,
)
from .readings import format_bp, parse_bp
from .textutil import (
    collapse_repeats,
    detect_language,
    has_any,
    marathi_evidence,
    normalize,
    tokens,
)
from .tools import weather, web_search


def _reply_language(language_code: str | None, text: str, default: str) -> str:
    """STT's language label, except that clearly Marathi words win over a hi-IN label (Prisma confuses the two)."""
    detected = _detected_reply_language(language_code)
    if detected in (None, "hi") and marathi_evidence(text) >= 1:
        return "mr"
    return detected or detect_language(text, default)


def _detected_reply_language(language_code: str | None) -> str | None:
    if not language_code:
        return None
    prefix = language_code.replace("_", "-").split("-", 1)[0].lower()
    return prefix if prefix in {"mr", "hi", "en", "bn", "gu", "kn", "ml", "pa", "ta", "te", "or"} else None


_SYSTEM_MARKER = re.compile(r"^\[(?:video_call_[a-z_]+|media_[a-z_]+|checkin:[^]]+)\]", re.I)
_NOISE = frozenset({"hmm", "hm", "umm", "uh", "अं", "हम्म"})


def _is_system_marker(text: str) -> bool:
    return bool(_SYSTEM_MARKER.match((text or "").strip()))

log = logging.getLogger("reasoning.turn")

_WEB_TURN_BUDGET_S = 8.5  # whole turn, understanding + search (<=4 s) + answer; the voice path waits 9 s
_WEB_ANSWER_RESERVE_S = 1.5  # kept back for the answer call when sizing the search timeout
_WEB_BLOCK = re.compile(
    r"औषध|गोळी|गोळ्या|डोस|इंजेक्शन|दवा|दवाई|खुराक|medicine|tablet|dose|injection|pill|"
    r"बीपी|शुगर|रक्तदाब|ब्लड|bp|sugar|diabet|मधुमेह|ताप|fever|दुखत|दर्द|pain|ऑपरेशन|surgery|"
    r"மருந்து|மாத்திரை|வலி|காய்ச்சல்|சர்க்கரை|"  # Tamil
    r"మందు|మాత్ర|నొప్పి|జ్వరం|చక్కెర|"  # Telugu
    r"ಔಷಧ|ಮಾತ್ರೆ|ನೋವು|ಜ್ವರ|ಸಕ್ಕರೆ|"  # Kannada
    r"മരുന്ന്|ഗുളിക|വേദന|പനി|പഞ്ചസാര|"  # Malayalam
    r"ওষুধ|ট্যাবলেট|ব্যথা|জ্বর|"  # Bengali
    r"દવા|ગોળી|દુખાવો|તાવ|"  # Gujarati
    r"ਦਵਾਈ|ਗੋਲੀ|ਦਰਦ|ਬੁਖਾਰ",  # Punjabi
    re.IGNORECASE,
)
_WEATHER = re.compile(r"पाऊस|पावस|हवामान|तापमान|थंडी|उकाडा|मौसम|बारिश|तापमान|weather|mausam|temperature|rain|\bpa+u?s\b|havaman|hawaman|b(?:a+)?rish", re.IGNORECASE)
_NEWS = re.compile(r"बातम्या|बातमी|खबर|समाचार|न्यूज|घडामोडी|headline|\bnews\b|batmya|batami|khabar", re.IGNORECASE)
# prepare(): a sentence that LOOKS like a live-facts question (weather, news, score, price, who holds an office)
_WEB_LIKELY = re.compile(
    _WEATHER.pattern + "|" + _NEWS.pattern + r"|स्कोर|सामना|मॅच|मैच|क्रिकेट|score|match|cricket|भाव|दर\b|किंमत|price|rate|"
    r"पंतप्रधान|मुख्यमंत्री|प्रधानमंत्री|prime minister|president|कोण जिंकल|आज काय चालू",
    re.IGNORECASE,
)
_MIN_LLM_BUDGET_S = 0.3  # less than this left in the turn's LLM budget: do not start a call
_UNDERSTAND_TIMEOUT_S = 3.0
_ACTION_CONFIDENCE_FLOOR = 0.4  # below this an LLM action intent is ignored and the rules decide
# What the LLM may SUGGEST for a turn the rules could not read. Medicines, confirmations, forgetting and
# sharing are deliberately absent: those come only from the deterministic parser.
_LLM_INTENTS = frozenset(
    {"CREATE_REMINDER", "LIST_TODAY", "GET_APPOINTMENT", "CALL_FAMILY_REMINDER", "VIDEO_CALL", "REQUEST_CAREGIVER", "CHAT",
     "DISTRESS"} | APP_INTENTS
)
_YT_MUSIC = ("youtube_playlist", "youtube_video", "youtube_query")  # what a song request may open (family favourites)
_YT_ALL = _YT_MUSIC + ("youtube_channel_live",)
_NEWS_SEARCH = "मराठी बातम्या live"  # core-api adds eventType=live for kind=news_video
_MEDIA_ASK_WINDOW_S = 120.0  # how long "काय लावू?" waits for her answer
_MEDIA_TITLE_WORDS = 6  # the spoken title after "लावतो:"
_CHOICE_WINDOW_S = 120.0  # how long the three cards stay answerable
_CHOICE_TITLE_WORDS = 5  # the spoken / card title: at most five words
# A short answer to the three cards. "दुसरं दाखव" is the next page, checked before the plain ordinals.
_CHOICE_MORE = ("दुसरं दाखव", "दुसरे दाखव", "अजून", "अजून दाखव", "आणखी", "पुढचं", "पुढचे", "more", "next")
_CHOICE_CANCEL = ("नको", "नका", "बंद", "बंद कर", "थांब", "थांबव", "cancel", "stop")
_CHOICE_ORDINALS = {
    0: ("पहिलं", "पहिला", "पहिली", "पहिले", "एक", "१", "1", "first", "one"),
    1: ("दुसरं", "दुसरा", "दुसरी", "दुसरे", "दोन", "२", "2", "second", "two"),
    2: ("तिसरं", "तिसरा", "तिसरी", "तिसरे", "तीन", "३", "3", "third", "three"),
}
_CHOICE_LAST = ("शेवटचं", "शेवटचा", "शेवटची", "शेवटी", "last")
# Words that appear in almost every card: matching one of them is not naming a card.
_CHOICE_STOP = frozenset(
    "गाणं गाणी गीत संगीत भजन अभंग आरती बातम्या बातमी न्यूज मराठी रेसिपी व्यायाम योग व्हिडिओ व्हिडीओ "
    "video song news recipe exercise yoga".split()
)


@dataclass
class _MediaChoice:
    """Three cards waiting for a spoken number / channel / title, or a tap. Per user, in memory, 2 minutes."""

    kind: str  # news | music | ...
    query: str
    items: list[dict[str, Any]]
    offset: int = 0
    at: float = 0.0


def _sentence(title: str) -> str:
    """A headline as one spoken sentence: unchanged words, and a full stop only when it has no ending of its own."""
    t = title.strip()
    return t if t.endswith((".", "!", "?", "।", "…")) else t + "."


def _short_title(title: str, max_words: int = _MEDIA_TITLE_WORDS) -> str:
    """At most six words of a YouTube title for the spoken line, without stray punctuation."""
    text = " ".join(title.split()[:max_words]).strip(" .,;:!?…-–—&|")
    return text or title.strip()[:60]


def _same_word(said: str, card: str) -> bool:
    """A spoken word names a card word: equal, or one is the start of the other ("ABP" ~ "ABP माझा")."""
    if said == card:
        return True
    short = min(len(said), len(card))
    return short >= 4 and (said.startswith(card) or card.startswith(said))


# Who a safety or help line names: the son first, then any other family member, NEVER a doctor, never an
# arbitrary first row. `_FAMILY_FALLBACK` is used when nothing fits.
_SON_WORDS = ("son", "मुलगा")
_DOCTOR_WORDS = ("doctor", "डॉक")
# Used only when the companion would say exactly what it said a moment ago.
def companion_name(user: dict[str, Any] | None) -> str:
    """What she calls Arjun: the family can rename him (Settings); blank = Arjun."""
    style = (user or {}).get("speech_style") or {}
    return str(style.get("companion_name") or "").strip() or "Arjun"


def rename_companion(text: str, name: str) -> str:
    if name == "Arjun":
        return text
    return text.replace("अर्जुन", name).replace("Arjun", name)


_NAME_QUESTIONS = ("तुझं नाव काय", "तुमचं नाव काय", "तुझे नाव काय", "तुझं नाव", "tujha nav", "tuza nav",
                   "तुम्हारा नाम", "आपका नाम", "तेरा नाम", "tumhara naam", "aapka naam", "your name",
                   "who are you", "तू कोण आहेस", "तुम्ही कोण आहात", "तुम कौन हो", "आप कौन हैं")

_VARIED = {
    "mr": ["हं, सांगा ना, मी ऐकतोय.", "बरं. मग पुढे काय झालं?", "अरे वा! जरा अजून सांगा.", "हो का? मग?"],
    "hi": ["हाँ, बताइए, मैं सुन रहा हूँ।", "अच्छा। फिर क्या हुआ?", "अरे वाह! थोड़ा और बताइए।", "हम्म, फिर?"],
    "en": ["I'm listening, go on.", "Oh? Then what happened?", "Tell me a little more.", "Mm, and then?"],
}

_FAMILY_FALLBACK = {"mr": "तुमच्या घरच्यांना", "hi": "आपके घरवालों को", "en": "your family"}
_VARIED.update(replies_langs.VARIED)
_FAMILY_FALLBACK.update(replies_langs.FAMILY)


def _is_son(relation: str) -> bool:
    rel = relation.lower()
    return any(w in rel for w in _SON_WORDS)


def _is_doctor(relation: str) -> bool:
    rel = relation.lower()
    return any(w in rel for w in _DOCTOR_WORDS)


NO_ACTION: dict[str, str] = {"type": "none", "kind": "", "value": "", "title": ""}
# Intents that may follow a pending question: answer it, or cancel it. A restated reminder is a correction of
# a pending reminder (see _answers_pending). Nothing else may touch, replace or sit on top of the question.
_ANSWERS = frozenset({"CONFIRM_YES", "CONFIRM_NO", "DECLINE_TOPIC", "FORGET_MEMORY"})
_SAFETY_HOLD_S = 120.0  # no reminder / medicine prompt is spoken this soon after a safety reply
_SAFETY_LLM_S = 2.0  # the second-layer safety check: past this the fail-safe words decide
_CHAT_QUIET_S = 120.0  # a check-in question is not asked within this long of her last turn
_CHECKIN_UNDERSTAND_S = 3.0  # the one LLM reading of an answer the word rules could not tell
_OFFER_WINDOW_S = 120.0  # "त्याला निरोप पाठवू का?" waits this long for her yes
_CONVO_WINDOW_S = 300.0  # a companion chat is "active" this long after its last companion turn
_SHORT_TURN_WORDS = 4  # a bare "झालं" / "झाला ना" is this short; a story sentence is longer
_HISTORY_CARE_CHARS = 140  # a care turn goes into the LLM history as short text only
# Bare answers that are not "stop talking": in a chat they are part of the chat. "नको" / "nako" stays a stop.
_SOFT_ANSWERS = frozenset({"CONFIRM_YES", "CONFIRM_NO"})
_STOP_NO = ("nako", "नको", "mat", "नही")
# First words that make a turn an answer to an open yes/no rather than a declarative sentence. "नाही, घेतली नाही"
# is an answer; "माझा चस्मा सापडत नाही" is a sentence that happens to end in "नाही".
_ANSWER_OPENERS = frozenset({
    "हो", "होय", "हं", "होते", "बरं", "ठीक", "करा", "लाव", "नाही", "नको", "नका", "थांब", "रद्द",
    "yes", "yeah", "yep", "ok", "okay", "sure", "no", "nope", "stop", "cancel",
})


def _looks_like_an_answer(text: str) -> bool:
    """True for a bare yes/no ("हो", "नको", "नाही, नको") or a two-word reply. A full sentence is not one."""
    words = normalize(text).split()
    if len(words) <= 2:
        return True
    return words[0].strip(".,!?;:").lower() in _ANSWER_OPENERS

_AI_QUESTIONS = (
    "are you human", "are you a robot", "are you real", "are you a person", "tu manus aahes ka",
    "tumhi manus aahat ka", "tu manus aahes", "तू माणूस आहेस का", "तुम्ही माणूस आहात का",
    "kya tum insaan ho", "kya aap insaan ho", "क्या तुम इंसान हो", "क्या आप इंसान हैं",
    "tu kon aahes", "तू कोण आहेस", "tum kaun ho", "तुम कौन हो", "who are you",
    "robot aahes ka", "रोबोट आहेस का", "machine ho kya", "ai aahes ka", "एआय आहेस का",
)


@dataclass
class TurnResult:
    reply: str
    intent: str
    mode: str  # care | companion | safety
    language: str
    awaiting_confirmation: bool = False
    source: str = "rules"  # rules | llm
    trace: dict[str, Any] = field(default_factory=dict)
    # Which Ghar screen the elder app shows: reply | story | confirm | saved | safety. Decided here, where it is
    # tested; the app only mirrors it. "safety" wins over everything.
    screen: str = "reply"
    # What the voice says, with Timbre v3.0 voice tags the LLM chose ("<laugh> ..."). Empty = say `reply`.
    # The screen always shows `reply` (no tags). The voice agent strips tags for TTS models without them.
    speech: str = ""
    # What the elder screen should OPEN or do: {type: open|control|choice|none, kind, value, title, choices?}.
    # Decided here from the family's app_links / core-api search (never from the LLM); the voice agent publishes it
    # as "arjun.action", the page performs it.
    action: dict[str, Any] = field(default_factory=lambda: dict(NO_ACTION))
    speech_style: dict[str, Any] = field(default_factory=lambda: {"rate": "normal", "volume": "normal", "simple": False})
    silent: bool = False
    # Spoken "बघतो…" for a turn that needed a live web lookup. The reply is only ready after the search, so a caller
    # that wants to say it first must play this before waiting; /turn itself still answers once.
    filler: str = ""


class TurnEngine:
    def __init__(
        self,
        core: CoreClient,
        evon: EvonClient | None = None,
        clock: Callable[[], datetime] = local_now,
        llm_timeout_s: float = config.LLM_TIMEOUT_S,
        history_exchanges: int = config.SESSION_EXCHANGES,
        mono: Callable[[], float] = time.monotonic,
        ask_first: bool = config.ASK_BEFORE_ACTING,
    ) -> None:
        self.core = core
        # False (default): act at once, read back in one line, "नको" undoes it. True: the old yes/no question.
        self.ask_first = ask_first
        self._last_done: dict[int, tuple[dict[str, Any], float]] = {}  # user -> (confirmed action, mono time)
        self._asked_dose: dict[int, tuple[int, float]] = {}  # user -> (dose id just announced, mono time)
        self.evon = evon  # the hosted LLM (name kept from the Evon days); None = rules only
        self.clock = clock
        self._llm_timeout_s = llm_timeout_s
        self._mono = mono
        self._llm_deadline = 0.0
        self._last_safety: dict[int, float] = {}  # user -> monotonic time of the last safety reply (T8)
        self._drafts: dict[int, Draft] = {}  # in-memory slot-filling state (single instance)
        self._media_ask: dict[int, float] = {}  # user -> mono time of "काय लावू?" waiting for the answer
        self._media_choice: dict[int, _MediaChoice] = {}  # user -> the three cards waiting for an answer
        self._chat_counter: dict[int, int] = {}
        self._noise_count: dict[int, int] = {}
        self._last_clarification: dict[int, tuple[str, float]] = {}
        self._convo_at: dict[int, float] = {}  # user -> monotonic time of the last companion turn
        self._last_turn: dict[int, float] = {}  # user -> monotonic time of her last turn (any kind)
        self._family_offer: dict[int, tuple[float, str, str]] = {}  # user -> (when, name, relation) of the offer
        # Session memory (memory.py): EVERY spoken line of this session, a running summary instead of deletion after a
        # long silence, the question Arjun is waiting on. In memory only, never stored. Long-term facts: self.facts.
        self.memory = SessionMemory(history_exchanges, config.SESSION_IDLE_MIN)
        self.facts = FactBook(core, mono)
        self._last_fact: dict[int, tuple[int, str, float]] = {}  # user -> (fact id, text, mono) she just saved
        self._delivered: dict[int, tuple[int, str, str]] = {}  # delivery id -> (user, spoken text, kind)
        self._local = threading.local()  # nested handle() calls (a check-in "yes" opens media) record only once
        # USER CONTEXT for the LLM: built from core-api, cached per user for five minutes, never persisted.
        self._context_cache: dict[int, tuple[float, str]] = {}
        self._last_arjun_reply: dict[int, str] = {}
        self._recent_replies: dict[int, list[str]] = {}
        self._listen_i: dict[int, int] = {}
        self._last_reply_simplifiable: dict[int, bool] = {}
        self._repeat_times: dict[int, deque[float]] = {}
        self._city_state: dict[int, tuple[str, str, float]] = {}  # uid -> ("ask"|"save", city, expires) after a weather turn

    # ------------------------------------------------------------------ public
    def _llm_remaining(self) -> float:
        """Seconds left of this turn's ONE LLM time budget (the voice path waits about 5 s in total)."""
        return max(0.0, self._llm_deadline - self._mono())

    def media_stopped(self, user_id: int) -> None:
        """Drop in-memory media answer state when the elder page reports playback ended."""
        self._media_ask.pop(user_id, None)
        self._media_choice.pop(user_id, None)
        self.memory.event(user_id, self.clock(), "[media stopped]")

    def video_call_stopped(self, user_id: int) -> None:
        """Clear media-related pending state when a call takes over the voice session."""
        self._media_ask.pop(user_id, None)
        self._media_choice.pop(user_id, None)

    def handle(self, user_id: int, text: str, language_code: str | None = None) -> TurnResult:
        """One turn. Whatever path answers (safety, rules, a tool, the LLM), the exchange is recorded ONCE in the session
        memory afterwards, so no spoken line is ever missing from the history the LLM sees."""
        depth = getattr(self._local, "depth", 0)
        self._local.depth = depth + 1
        try:
            res = self._handle(user_id, text, language_code)
        finally:
            self._local.depth = depth
        if depth == 0:
            res = self._vary_repeat(user_id, res)
            try:
                self._record_turn(user_id, text, res)
            except Exception as exc:  # noqa: BLE001 - memory must never break the turn
                log.warning("could not record the turn in session memory: %s", type(exc).__name__)
            if res.intent not in ("REPEAT", "SPEAK_SLOWER", "SPEAK_LOUDER", "SPEAK_NORMAL") and res.reply:
                self._last_arjun_reply[user_id] = res.reply
                self._last_reply_simplifiable[user_id] = res.intent == "CHAT" and res.mode == "companion"
        return res

    def _vary_repeat(self, user_id: int, res: TurnResult) -> TurnResult:
        """A companion chat line never repeats one of Arjun's last 3 lines word for word (heard live 2026-11-08: the
        same sentence four times sounded like a machine). Safety and care templates are never touched."""
        recent = self._recent_replies.setdefault(user_id, [])
        if res.mode == "companion" and res.intent in ("CHAT", "UNKNOWN") and res.reply and res.reply in recent:
            pool = _VARIED.get(res.language, _VARIED["mr"])
            fresh = next((x for x in pool if x not in recent), pool[len(recent) % len(pool)])
            res = replace(res, reply=fresh)
        if res.reply:
            recent.append(res.reply)
            del recent[:-3]
        return res

    def _handle(self, user_id: int, text: str, language_code: str | None = None) -> TurnResult:
        t0 = time.perf_counter()
        self._llm_deadline = self._mono() + self._llm_timeout_s
        self._last_turn[user_id] = self._mono()
        text = collapse_repeats(text)  # recognizer artifacts ("हो हो हो कर कर कर ...") before ANY parsing or safety check
        trace: dict[str, Any] = {}
        if text.strip().casefold().startswith("[video_call_missed]"):
            name = text.partition("]")[2].strip()[:80] or "घरच्यांनी"
            return TurnResult(f"{name}नी उचलला नाही, मी निरोप ठेवला आहे.", "VIDEO_CALL_MISSED", "care", "mr")
        if _is_system_marker(text):
            log.info("ignoring system marker in turn")
            return TurnResult("", "SYSTEM_EVENT", "care", "mr", trace={"silent": True}, silent=True)
        if not text.strip() or normalize(text) in _NOISE:
            count = self._noise_count.get(user_id, 0) + 1
            self._noise_count[user_id] = count
            if count < 2:
                log.info("turn silent: empty/noise transcript")
                return TurnResult("", "NOISE", "care", _detected_reply_language(language_code) or "mr", silent=True)
            self._noise_count[user_id] = 0
            language = _detected_reply_language(language_code) or "mr"
            prompt = {"mr": "आवाज नीट आला नाही, जरा जवळ येऊन सांगाल?", "hi": "आवाज़ ठीक से नहीं आई, ज़रा पास आकर बताएँगे?", "en": "I couldn't hear that clearly. Could you come a little closer and tell me?"}
            prompt.update(replies_langs.NOISE)
            return TurnResult(prompt.get(language, prompt["mr"]), "NOISE", "companion", language)
        self._noise_count[user_id] = 0
        # 0/1. emergency, then distress: both override everything and must not depend on
        # core-api being reachable. The replies are fixed templates, so a failed lookup only
        # costs the language default.
        emergency = is_emergency(text)
        distress = not emergency and (
            is_distress(text) or "त्रास" in text and ("होतोय" in text or "होते" in text or "होता" in text)
        )
        if not (emergency or distress):  # second layer: a body / health word no rule recognised
            verdict = self._second_look(text)
            emergency, distress = verdict == "emergency", verdict == "distress"
        if emergency or distress:
            self._media_choice.pop(user_id, None)  # an emergency closes the cards: nothing is playing
            try:
                default_lang = self.core.user(user_id)["language"]
            except (CoreError, httpx.HTTPError, KeyError):
                default_lang = "mr"
            lang = _reply_language(language_code, text, default_lang)
            if emergency:
                return self._safety(user_id, lang, trace, t0, kind="emergency")
            return self._distress(user_id, lang, trace, t0)

        # core-api down must never mean silence: answer with the fixed error template instead.
        try:
            user = self.core.user(user_id)
        except (CoreError, httpx.HTTPError) as exc:
            log.error("core-api unavailable for user lookup: %s", exc)
            lang = detect_language(text, "mr")
            r = rp.R[rp.lang_or_default(lang)]
            return TurnResult(r["error"], "UNKNOWN", "care", lang, trace=self._t(trace, t0))
        lang = _reply_language(language_code, text, user["language"])
        r = rp.R[rp.lang_or_default(lang)]
        now = self.clock()
        style = user.get("speech_style") or {"rate": "normal", "volume": "normal", "simple": False}
        norm_text = normalize(text)
        if any(x in norm_text for x in ("नेहमीसारखं बोल", "नेहमी सारखं बोल", "normal bol")):
            style = {"rate": "normal", "volume": "normal", "simple": False,
                     "companion_name": str(style.get("companion_name") or "")}  # the family-set name stays
            self._save_speech_style(user_id, style)
            return TurnResult("ठीक आहे, नेहमीसारखं बोलतो.", "SPEAK_NORMAL", "care", lang, speech_style=style)
        if any(x in norm_text for x in ("हळू बोल", "हळू बोला", "slow bol", "मोठ्याने बोल", "मोठ्याने बोला", "नीट ऐकू येत नाही")):
            style = dict(style)
            slow_request = "हळू" in norm_text or "slow" in norm_text
            if slow_request:
                style["rate"] = "slow"
            else:
                style["volume"] = "loud"
            self._save_speech_style(user_id, style)
            answer = "ठीक आहे. आता हळू बोलतो." if slow_request else "ठीक आहे. आवाज वाढवतो."
            return TurnResult(answer, "SPEAK_SLOWER" if slow_request else "SPEAK_LOUDER", "care", lang, speech_style=style)
        if self._is_repeat_request(norm_text):
            times = self._repeat_times.setdefault(user_id, deque())
            now_mono = self._mono()
            while times and now_mono - times[0] > 600:
                times.popleft()
            times.append(now_mono)
            if len(times) >= 2 and (not style.get("simple") or style.get("rate") != "slow"):
                style = {**style, "rate": "slow", "simple": True}
                self._save_speech_style(user_id, style)
            original = self._last_arjun_reply.get(user_id, "")
            repeated = original
            simplify = getattr(self.evon, "simplify_reply", None)
            if original and self._last_reply_simplifiable.get(user_id, False) and callable(simplify) and self._llm_remaining() > 0:
                try:
                    candidate = simplify(original, lang, timeout=self._llm_remaining())
                    if candidate and self._same_numbers(original, candidate):
                        repeated = candidate
                except Exception:  # noqa: BLE001 - repeat falls back to exact same line
                    pass
            return TurnResult(repeated or "काय पुन्हा सांगू?", "REPEAT", "care", lang, speech_style=style)
        if text.strip().casefold().startswith("[video_call_missed]"):
            name = text.partition("]")[2].strip()[:80] or "घरच्यांनी"
            return TurnResult(f"{name}नी उचलला नाही, मी निरोप ठेवला आहे.", "VIDEO_CALL_MISSED", "care", lang)
        if self._is_greeting(text):
            self.facts.invalidate(user_id)  # the idle flush may just have saved yesterday's fact

        # 2a. "हे लक्षात ठेव" / "हे विसरून जा": her own words decide, rules only, no LLM call
        remembered = self._memory_command(user_id, text, lang, now, trace, t0)
        if remembered is not None:
            return remembered

        # 2b. the answer to "which city?" / "keep it?" after a weather turn: short, deterministic, no LLM
        if user_id in self._city_state:
            city_turn = self._city_followup(user_id, text, lang, trace, t0)
            if city_turn is not None:
                return city_turn

        # 3. ONE LLM call for every non-safety turn: the whole sentence, this conversation's history and the
        # family/dashboard context together. The rules are only the fallback (no LLM, timeout, bad JSON, or a
        # low-confidence action intent). Safety above this line never waits for the model.
        llm, llm_reason, llm_attempted = self._understand(user_id, text, lang, now, user)
        trace["route"] = "llm" if llm else "rules"
        if llm is None:
            trace["route_reason"] = llm_reason

        # 2. AI disclosure (and "what is your name?", answered with the same honest line)
        if has_any(normalize(text), _AI_QUESTIONS) or has_any(normalize(text), _NAME_QUESTIONS):
            return TurnResult(rename_companion(r["ai_disclosure"], companion_name(user)), "UNKNOWN", "care", lang,
                              trace=self._t(trace, t0))

        offered = self._family_offer_answer(user_id, text, lang, trace, t0, llm)
        if offered is not None:
            return offered

        profile = Profile(user["wake_time"], user["lunch_time"], user["dinner_time"], lang)
        try:
            pending = self.core.pending(user_id)
        except (CoreError, httpx.HTTPError) as exc:
            log.error("core-api unavailable for pending lookup: %s", exc)
            return TurnResult(r["error"], "UNKNOWN", "care", lang, trace=self._t(trace, t0))
        draft = self._drafts.get(user_id)
        recent = self._recent_done(user_id)
        if pending is not None or draft is not None:
            self._media_choice.pop(user_id, None)  # a reminder / medicine question wins over the cards
        else:
            picked = self._answer_choice(user_id, text, lang, trace, t0, llm)
            if picked is not None:
                if picked.intent == "CHAT" and picked.mode == "companion":
                    self._convo_at[user_id] = self._mono()
                log.info(json.dumps({"user": user_id, "intent": picked.intent, **picked.trace}))
                return picked
        # A meal / walk prompt that a session really spoke takes a clear done/skipped answer - but only when
        # nothing else is waiting: no yes/no, no reminder draft, no undo window, no recent medicine prompt.
        if pending is None and draft is None and recent is None and self._recent_dose(user_id) is None:
            reading = self._record_bp(user_id, text, lang, trace, t0, llm)
            if reading is not None:
                return reading
            checkin = self._answer_open_checkin(user_id, text, lang, trace, t0, llm)
            if checkin is not None:
                return checkin
        self._note_volunteered(user_id, text, now)
        answerable = pending["action_type"] if pending else (recent["action_type"] if recent else None)
        if answerable is None and self._recent_dose(user_id) is not None:
            answerable = "MEDICINE_TAKEN"  # "हो" / "घेतली" right after a medicine prompt
        conversing = pending is None and draft is None and self._conversing(user_id)
        parsed, source = self._intent(
            text, profile, now, lang, answerable is not None, draft, answerable, conversing=conversing,
            llm=llm, llm_attempted=llm_attempted,
        )
        if pending is None and draft is None and parsed.intent in (OPEN_MEDIA, OPEN_LINK, "CHAT", "UNKNOWN"):
            # A named phone app with an open/play verb is exact words, not a guess: the rule wins over the model's
            # generic "media"/"chat" ("स्पॉटिफायवर भजन लाव" must not become a YouTube search).
            app_cmd = parse_app_command(text)
            if app_cmd is not None and app_cmd.intent == OPEN_APP:
                parsed = Parsed(OPEN_APP, 0.9, lang, parsed.draft, topic=app_cmd.topic, query=app_cmd.query)
        if pending is None and draft is None:
            parsed = self._use_media_answer(user_id, text, parsed)
        else:
            self._media_ask.pop(user_id, None)
        if pending is None and draft is None:
            parsed = self._reshape(user_id, text, parsed, conversing)
            parsed = self._unmatched_link_is_chat(user_id, text, parsed)
        trace["intent_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        if parsed.intent == "DISTRESS":
            return self._distress(user_id, lang, trace, t0)
        if parsed.intent == "SYMPTOM" and answerable != "MEDICINE_TAKEN":
            # A health complaint wins over whatever question was open; the pending action stays open and is
            # asked again later. "नाही" to the medicine question is handled by the rule branch above.
            category = symptom_category(text) or "unwell"
            return self._symptom(user_id, text, category, lang, trace, t0, now)
        if pending is not None and not self._answers_pending(parsed.intent, pending):
            return self._repeat_pending(user_id, pending, lang, now, trace, t0)
        # 3b. a health complaint, then loneliness: only when nothing else was asked for (a care command or a pending
        # question wins). Never advice: a fixed warm line + a family note (consent) and the chat goes on.
        if pending is None and draft is None and parsed.intent in ("CHAT", "UNKNOWN"):
            category = symptom_category(text)
            if category:
                return self._symptom(user_id, text, category, lang, trace, t0, now)
            if is_lonely(text):
                return self._lonely(user_id, text, lang, trace, t0, now)

        # 3c. live facts (weather, news, scores): only on the LLM's say-so, only after every safety path above
        if pending is None and draft is None and parsed.intent == "CHAT" and llm and llm.get("needs_web"):
            web = self._web_turn(user_id, text, str(llm.get("web_query") or ""), lang, trace, t0)
            if web is not None:
                self._convo_at[user_id] = self._mono()
                return web

        # 4. dispatch
        try:
            result = self._dispatch(user_id, text, parsed, pending, draft, profile, now, lang, llm)
        except CoreError as exc:
            log.warning("core error: %s", exc)
            # a half-built reminder must not swallow her next sentences (seen in the 2026-10-31 smoke run)
            self._drafts.pop(user_id, None)
            result = TurnResult(r["error"], parsed.intent, "care", lang)
        if result.source != "llm" and not (result.intent == "CHAT" and result.mode == "companion"):
            result.source = source  # a companion reply keeps its own provenance (LLM or fixed fallback)
        result.trace = self._t({**trace, "intent": parsed.intent}, t0)
        if result.intent == "CHAT" and result.mode == "companion":
            self._convo_at[user_id] = self._mono()
        if result.mode != "safety":
            guarded = self._guard_cardiac_reply(user_id, text, result, lang, trace, t0)
            if guarded is not None:
                return guarded
        log.info(json.dumps({"user": user_id, "intent": parsed.intent, **result.trace}))
        result.speech_style = style
        return result

    @staticmethod
    def _is_repeat_request(text: str) -> bool:
        return text.strip() == "काय" or any(x in text for x in ("पुन्हा सांग", "परत सांग", "समजलं नाही", "समजले नाही"))

    @staticmethod
    def _same_numbers(before: str, after: str) -> bool:
        pattern = r"(?<!\w)(?:\d{1,2}:\d{2}|\d+(?:[.,]\d+)?)(?!\w)"
        return re.findall(pattern, before) == re.findall(pattern, after)

    def _save_speech_style(self, uid: int, style: dict[str, Any]) -> None:
        try:
            self.core.patch_user(uid, {"speech_style": style})
        except (CoreError, httpx.HTTPError) as exc:
            log.warning("could not save speech preference (%s)", type(exc).__name__)

    # ------------------------------------------------------------------ LLM-first understanding
    def _understand(
        self, uid: int, text: str, lang: str, now: datetime, user: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str, bool]:
        """One LLM reading of this turn, or None + why + whether a call was attempted.

        `attempted` matters: when the unified call was tried and failed we must NOT call the old intent
        extractor as a second model call; the rule parser answers instead.
        """
        if self.evon is None:
            return None, "no_llm", False
        if not hasattr(self.evon, "understand_turn"):
            return None, "legacy_client", False  # a fake/old provider: the old path decides
        if self._llm_remaining() < _MIN_LLM_BUDGET_S:
            return None, "no_budget", True
        view = self.memory.view(uid, now)
        context = self._user_context(uid, now, user, text)
        try:
            data = self.evon.understand_turn(  # type: ignore[attr-defined]
                text, lang, now, history=view.messages, context=context,
                interests=user.get("interests") or [],
                timeout=min(_UNDERSTAND_TIMEOUT_S, self._llm_remaining()), memory=view.block,
            )
        except httpx.TimeoutException:
            remaining = self._llm_remaining()
            if remaining < _MIN_LLM_BUDGET_S:
                log.info("understanding retry skipped: turn budget exhausted")
                return None, "timeout", True
            log.info("understanding timeout; retrying with compact recent context")
            try:
                data = self.evon.understand_turn(  # type: ignore[attr-defined]
                    text, lang, now, history=view.messages[-12:], context=context,
                    interests=user.get("interests") or [], timeout=remaining, memory=view.block,
                )
            except httpx.TimeoutException:
                log.info("understanding retry timed out")
                return None, "timeout_retry", True
            except httpx.HTTPError as exc:
                log.info("understanding retry failed: %s", type(exc).__name__)
                return None, "provider_error_retry", True
            except Exception as exc:  # noqa: BLE001 - malformed or broken providers must not break a turn
                log.info("understanding retry failed: %s", type(exc).__name__)
                return None, "error_retry", True
        except httpx.HTTPError as exc:
            cause = "llm_busy" if isinstance(exc, LlmBusy) else type(exc).__name__
            log.info("understanding fallback cause=%s", cause)
            return None, cause, True
        except Exception as exc:  # noqa: BLE001 - a slow/broken provider never breaks the turn
            log.info("llm understanding failed: %s", type(exc).__name__)
            return None, "error", True
        if not isinstance(data, dict):
            return None, "invalid_json", True
        intent = str(data.get("intent") or "")
        if intent not in (
            "chat", "reminder_add", "reminder_done", "medicine_taken", "medicine_query", "media", "news",
            "call_family", "message_family", "today_query", "undo", "stop", "health_complaint", "unclear",
        ):
            return None, "bad_intent", True
        try:
            confidence = float(data.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if intent not in ("chat", "unclear") and confidence < _ACTION_CONFIDENCE_FLOOR:
            return None, "low_confidence", True
        return data, "ok", True

    def _user_context(self, uid: int, now: datetime, user: dict[str, Any], text: str = "") -> str:
        """The cached family/dashboard context plus the facts she told Arjun that fit THIS sentence (never cached)."""
        base = self._base_context(uid, now, user)
        facts = self.facts.block(uid, text, now, config.FACTS_IN_CONTEXT)
        context = f"{base}\n{facts}" if facts else base
        if text and self._is_greeting(text):
            followup = self._yesterday_followup(uid, now)
            if followup:
                context += (
                    "\nFIRST GREETING FOLLOW-UP: Refer naturally to this one most recent unresolved item from yesterday, "
                    "and ask how it went. Do not introduce another event: " + followup
                )
        return context

    @staticmethod
    def _is_greeting(text: str) -> bool:
        norm = normalize(text)
        return has_any(norm, ("नमस्कार", "नमस्ते", "हॅलो", "हेलो", "hello", "namaste", "namaskar"))

    def _yesterday_followup(self, uid: int, now: datetime, *, refresh: bool = False) -> str:
        """Deterministically choose yesterday's latest event fact, then a yesterday summary topic as fallback."""
        if refresh:
            self.facts.invalidate(uid)
        yesterday = (now.date() - timedelta(days=1)).isoformat()
        events = [f for f in self.facts.all(uid) if f.get("kind") == "event" and str(f.get("source_date"))[:10] == yesterday]
        if events:
            selected = max(events, key=lambda f: (str(f.get("source_date")), int(f.get("id") or 0)))
            return str(selected.get("fact") or "")[:160]
        try:
            rows = self.core.wellbeing_recent(uid, days=2)
            for row in rows:
                if str(row.get("kind")) != "conversation" or str(row.get("created_at") or "")[:10] != yesterday:
                    continue
                topic = str(row.get("summary") or "").strip()
                if topic and topic != "Talked with Arjun.":
                    return topic[:160]
        except (CoreError, httpx.HTTPError, AttributeError):
            pass
        return ""

    def _story_recall(self, uid: int, text: str) -> str:
        """RAG over HER OWN saved stories only (boundary 2: past stories, never reminders or medicines). The text comes
        from stored rows, so Arjun can refer to a past story but never invent one. Any failure means no recall."""
        if len(text.strip()) < 6:
            return ""
        try:
            hits = self.core.search_stories(uid, text, 2)
        except Exception:  # core-api down or an older core: the reply just has no memory block
            return ""
        lines = [str(h.get("summary", "")).strip()[:240] for h in hits if h.get("summary")]
        if not lines:
            return ""
        return (
            "\nHER OWN PAST STORIES (stored text, related to what she just said). Mention one only if it fits "
            "naturally; use only these words, never add details or invent a memory: " + " | ".join(lines)
        )

    def _base_context(self, uid: int, now: datetime, user: dict[str, Any]) -> str:
        """A short, private context block for the companion LLM (<=700 chars), cached for five minutes.

        Only what helps a reply: how to address her, family names/relations (never numbers), the date/day,
        today's medicines and check-ins, today's appointments/reminders, interests and the last conversation
        summary. No transcript, no phone number, no medical detail beyond what the family already recorded.
        """
        hit = self._context_cache.get(uid)
        if hit is not None and self._mono() - hit[0] < config.USER_CONTEXT_TTL_S:
            return hit[1]
        parts: list[str] = []
        name = re.sub(r"\s*\([^)]*\)", "", str(user.get("name") or "")).strip()
        address_as = str(user.get("address_as") or "").strip()
        if not address_as:
            first = name.split()[0] if name else ""
            # "हीराबाई" already carries बाई: never "हीराबाईबाई" (heard on the laptop 2026-11-08).
            honorific = first if first.endswith("बाई") else f"{first}बाई"
            address_as = "आजी" if user.get("age") is not None and int(user["age"]) >= 60 else honorific
        if name:
            parts.append(f"Name: {name}; address her as {address_as}")
        parts.append(f"your name: {companion_name(user)}")
        try:
            contacts = self.core.contacts(uid) or []
            family = [
                f"{c.get('name')} ({c.get('relation')})" for c in contacts
                if c.get("name") and "doctor" not in str(c.get("relation", "")).lower()
            ]
            if family:
                parts.append("Family: " + ", ".join(family[:6]))
        except (CoreError, httpx.HTTPError):
            pass
        parts.append(f"Today: {now:%A} {now.date().isoformat()}")
        if user.get("interests"):
            parts.append("Interests: " + ", ".join(str(x) for x in user["interests"][:4]))
        try:
            card = self.core.checkin_card(uid) or []
            meds = [
                f"{i.get('label') or i.get('kind')}: {i.get('state')}"
                for i in card if str(i.get("kind")) == "medicine"
            ]
            if meds:
                parts.append("Medicines today: " + ", ".join(meds[:6]))
            meals = [
                f"{i.get('kind')}: {i.get('state')}" for i in card
                if str(i.get("kind")) in ("sleep", "breakfast", "lunch", "dinner", "walk", "bp")
            ]
            if meals:
                parts.append("Check-ins: " + ", ".join(meals[:6]))
        except (CoreError, httpx.HTTPError):
            pass
        try:
            day = self.core.day(uid)
            rows = [
                f"{i['at'][11:16]} {i.get('label') or i.get('kind')}"
                for i in day.get("items", [])
                if i.get("kind") in ("appointment", "reminder", "medicine")
                and i.get("status") not in ("done", "taken", "unconfirmed")
            ]
            if rows:
                parts.append("On today: " + "; ".join(rows[:5]))
        except (CoreError, httpx.HTTPError):
            pass
        try:
            w = self.core.wellbeing_today(uid) or {}
            summary = str(w.get("last_summary") or "").strip()
            if summary:
                parts.append("Last conversation: " + summary[:160])
        except (CoreError, httpx.HTTPError):
            pass
        context = "\n".join(parts)
        if len(context) > config.USER_CONTEXT_MAX_CHARS:
            context = context[: config.USER_CONTEXT_MAX_CHARS].rsplit(" ", 1)[0]
        self._context_cache[uid] = (self._mono(), context)
        return context

    # ------------------------------------------------------------------ "हे लक्षात ठेव" / "हे विसरून जा"
    def _memory_command(
        self, uid: int, text: str, lang: str, now: datetime, trace: dict[str, Any], t0: float
    ) -> TurnResult | None:
        """Save a fact on her explicit word, or forget one. One read-back line, no question, rules only. core-api
        refuses numbers, addresses, money, medicines and diagnoses (and a body complaint without the consent flag)."""
        r = rp.R[rp.lang_or_default(lang)]

        def out(reply: str, intent: str) -> TurnResult:
            return TurnResult(reply, intent, "care", lang, trace=self._t(trace, t0))

        content = parse_remember(text)
        if content is not None:
            content = (content or self.memory.last_user_text(uid)).strip()[:140]
            if not content:
                return out(r["memory_what"], "MEMORY_ASK")
            kind = "concern" if symptom_category(content) else "note"
            try:
                saved = self.core.save_fact(uid, content, kind, 1.0, "explicit", now.date().isoformat())
            except CoreError as exc:
                if exc.status == 422:
                    return out(r["memory_refused"], "MEMORY_REFUSED")
                raise
            self.facts.invalidate(uid)
            self._last_fact[uid] = (int(saved["id"]), str(saved["fact"]), self._mono())
            return out(r["memory_saved"].format(fact=saved["fact"]), "MEMORY_SAVED")

        content = parse_forget(text)
        if content is None:
            return None
        gone: list[dict[str, Any]] = []
        last = self._last_fact.get(uid)
        if content:
            gone = self.core.forget_facts(uid, content)
        elif last is not None and self._mono() - last[2] < _OFFER_WINDOW_S * 5:
            try:
                self.core.delete_fact(uid, last[0])
                gone = [{"fact": last[1]}]
            except CoreError as exc:
                if exc.status != 404:
                    raise
        if not gone:
            return None  # not about a fact: "हे विसरून जा" keeps deleting the last story, as before
        self._last_fact.pop(uid, None)
        self.facts.invalidate(uid)
        self.memory.scrub(uid, str(gone[0]["fact"]))
        return out(r["memory_forgot"].format(fact=gone[0]["fact"]), "MEMORY_FORGOT")

    # ------------------------------------------------------------------ second layer and reply guard
    def _second_look(self, text: str) -> str | None:
        """For a turn the rules did not flag but that has a body / health word: ask the LLM for a strict-JSON
        {emergency, distress} verdict (2 s). Returns "emergency", "distress" or None.

        FAIL-SAFE: with no LLM, a timeout, a rate limit or unusable JSON, the words in distress.FAILSAFE_WORDS
        (attack / अटॅक / छाती / श्वास / बेशुद्ध ...) count as an emergency. A complaint the symptom flow already handles
        ("डोकं दुखतं") skips the call. The LLM only classifies: it never writes a reply here."""
        if not has_health_word(text):
            return None
        failsafe = has_failsafe_word(text)
        if symptom_category(text) and not failsafe:
            return None
        verdict = None
        if self.evon is not None and hasattr(self.evon, "safety_check"):
            try:
                verdict = self.evon.safety_check(text, timeout=_SAFETY_LLM_S)  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001 - never let the safety net itself break the turn
                log.warning("safety check failed (%s): fail-safe words decide", type(exc).__name__)
        if isinstance(verdict, dict) and isinstance(verdict.get("emergency"), bool) and isinstance(verdict.get("distress"), bool):
            return "emergency" if verdict["emergency"] else "distress" if verdict["distress"] else None
        return "emergency" if failsafe else None

    def _guard_cardiac_reply(
        self, uid: int, said: str, result: TurnResult, lang: str, trace: dict[str, Any], t0: float
    ) -> TurnResult | None:
        """The LLM never answers a heart attack, chest pain or stroke itself. A reply that carries medical advice for
        one (aspirin, "lie down", "breathe deeply" ...) is replaced: by the emergency flow when SHE spoke of it, by the
        fixed "ask the doctor" line when only the reply did. Rules and fixed templates are never touched."""
        if result.source != "llm" and result.mode != "companion":
            return None
        if not gives_medical_advice(result.reply) or not (mentions_cardiac(said) or mentions_cardiac(result.reply)):
            return None
        log.warning("guard: a reply with medical advice for a cardiac complaint was replaced (user %s)", uid)
        if mentions_cardiac(said):
            return self._safety(uid, lang, trace, t0, kind="emergency")
        r = rp.R[rp.lang_or_default(lang)]
        return TurnResult(r["med_deflect"], "MEDICAL_QUESTION", "care", lang, awaiting_confirmation=True,
                          screen="confirm", trace=self._t(trace, t0))

    # ------------------------------------------------------------------ conversation mode
    def _conversing(self, uid: int) -> bool:
        """A companion chat is going: its last companion turn was under five minutes ago."""
        at = self._convo_at.get(uid)
        return at is not None and self._mono() - at < _CONVO_WINDOW_S

    def _reshape(self, uid: int, text: str, p: Parsed, conversing: bool) -> Parsed:
        """Keep a story a story. Only ever turns a guess into CHAT; safety and explicit care commands are untouched.

        - "झालं" / "झाला ना" inside a story is not "mark my reminder done": COMPLETE_REMINDER needs an open
          reminder today whose words she actually said (a bare 1-4 word "झालं" outside a chat still closes the
          one open reminder, as before).
        - In a chat, a bare yes / no that answers nothing (no pending question, no undo window, no medicine
          prompt), a greeting and any short or odd turn are part of the chat. "नको" still stops the chat.
        """
        norm = normalize(text)
        if p.intent == "COMPLETE_REMINDER":
            if has_any(norm, MED_TAKEN_WORDS) and self._dose_due(uid):
                return p  # "घेतली" while a family-set dose is due is the medicine
            if self._names_an_open_reminder(uid, norm):
                return p
            bare = len(tokens(norm)) <= _SHORT_TURN_WORDS
            if bare and not conversing and self._single_open_reminder(uid):
                return p  # the old behaviour for a lone "झालं"
            return Parsed("CHAT", 0.5, p.language, p.draft)
        if not conversing:
            return p
        if p.intent in _SOFT_ANSWERS and not has_any(norm, _STOP_NO):
            if self._recent_done(uid) is None and self._recent_dose(uid) is None:
                return Parsed("CHAT", 0.5, p.language, p.draft)
        if p.intent in ("GREETING", "UNKNOWN"):
            return Parsed("CHAT", 0.5, p.language, p.draft)
        return p

    # ------------------------------------------------------------------ apps by voice
    def _use_media_answer(self, uid: int, text: str, p: Parsed) -> Parsed:
        """After "काय लावू? गाणं, भजन की बातम्या?" the next short answer is the query: "भजन" / "लता मंगेशकर"."""
        asked = self._media_ask.get(uid)
        if asked is None:
            return p
        if self._mono() - asked > _MEDIA_ASK_WINDOW_S:
            self._media_ask.pop(uid, None)
            return p
        if p.intent not in ("CHAT", "UNKNOWN", "NEWS_READ"):
            self._media_ask.pop(uid, None)  # a real command wins; the question is abandoned
            return p
        self._media_ask.pop(uid, None)
        if p.intent == "NEWS_READ":  # "बातम्या" answers "गाणं, भजन की बातम्या?" with the news on screen
            return Parsed("OPEN_MEDIA", 0.85, p.language, topic="news_video")
        query = clean_query(text)
        if not query:
            return p
        specific = media_specific(query, media_kind(text), query)
        return Parsed(
            "OPEN_MEDIA", 0.85, p.language, topic="youtube", query=query, media_specific=specific
        )

    def _unmatched_link_is_chat(self, uid: int, text: str, p: Parsed) -> Parsed:
        """A generic "... दाखव" that names nothing the family added is just talk, not "I could not find that"."""
        if p.intent != OPEN_LINK:
            return p
        try:
            links = self.core.app_links(uid)
        except (CoreError, httpx.HTTPError):
            links = []
        if self._named_links(links, text, p.query, kinds=("link",) + _YT_ALL):
            return p
        return Parsed("CHAT" if len(tokens(normalize(text))) >= 5 else "UNKNOWN", 0.4, p.language, p.draft)

    @staticmethod
    def _link_names(link: dict[str, Any]) -> list[str]:
        return [link["label"], *link.get("spoken_names", [])]

    def _named_links(
        self, links: list[dict[str, Any]], text: str, query: str, kinds: tuple[str, ...]
    ) -> list[dict[str, Any]]:
        """Family links of these kinds whose label / spoken name she said (with any ending), or the LLM's `query` label."""
        found = []
        for link in links:
            if link["kind"] not in kinds:
                continue
            if any(name_matches(n, text) or (query and name_matches(n, query)) for n in self._link_names(link)):
                found.append(link)
        return found

    @staticmethod
    def _open_link(link: dict[str, Any]) -> dict[str, str]:
        """The action for one of the family's rows: an id or an https URL, both validated by core-api."""
        return {"type": "open", "kind": link["kind"], "value": link["value"], "title": link["label"]}

    def _app_command(self, uid: int, text: str, p: Parsed, lang: str) -> TurnResult:
        """YouTube, news aloud, WhatsApp, a family link, stop/next/volume. Fixed lines; what opens comes from the family's
        app_links, never from the LLM. Every failure is a fixed line too (never silence, never a claim that it opened)."""
        a = A[rp.lang_or_default(lang)]

        def res(line: str, action: dict[str, str] | None = None) -> TurnResult:
            return TurnResult(line, p.intent, "care", lang, screen="reply", action=action or dict(NO_ACTION))

        if p.intent == MEDIA_CONTROL:
            kind = p.topic if p.topic in CONTROLS else "stop"
            return res(a[kind], {"type": "control", "kind": kind, "value": "", "title": ""})
        try:
            if p.intent == NEWS_READ:
                return self._read_news(uid, a, res)
            links = self.core.app_links(uid)
            if p.intent == OPEN_WHATSAPP:
                return self._open_whatsapp(uid, text, p, links, a, res)
            if p.intent == OPEN_APP:
                return self._open_app(p, links, a, res)
            if p.intent == OPEN_LINK:
                found = self._named_links(links, text, p.query, kinds=("link",) + _YT_ALL)
                if not found:
                    return res(a["link_none"])
                return res(
                    a["link_open"].format(label=found[0]["label"]),
                    {**self._open_link(found[0]), "label": found[0]["label"]},
                )
            return self._open_media(uid, text, p, links, a, res)
        except (CoreError, httpx.HTTPError) as exc:
            log.warning("app command failed: %s", exc)
            return res(a["app_unavailable"])

    @staticmethod
    def _open_app(
        p: Parsed, links: list[dict[str, Any]], a: dict[str, str], res: Callable[..., TurnResult]
    ) -> TurnResult:
        """A phone app (Spotify, JioSaavn, YouTube Music, Maps) the family approved. The page builds the link from
        its own table and asks for one tap; Arjun never says it opened."""
        app_id = p.topic or ""
        row = next((link for link in links if link["kind"] == "app" and link["value"] == app_id), None)
        name = (row or {}).get("label") or app_label(app_id)
        if row is None:
            return res(a["app_not_added"].format(app=name))
        line = a["app_search"].format(app=name, query=p.query) if p.query else a["app_open"].format(app=name)
        return res(line, {"type": "open", "kind": "app", "value": app_id, "title": name, "query": p.query})

    def _read_news(self, uid: int, a: dict[str, str], res: Callable[..., TurnResult]) -> TurnResult:
        try:
            items = self.core.news(uid)
        except (CoreError, httpx.HTTPError) as exc:
            log.warning("news unavailable: %s", exc)
            items = []
        if not items:
            return res(a["news_none"])
        lines = [a["news_item"].format(source=i["source_label"], title=_sentence(i["title"])) for i in items[:5]]
        return res(" ".join([a["news_intro"], *lines]))  # verbatim titles, source first, one per sentence; no LLM

    def _open_whatsapp(
        self, uid: int, text: str, p: Parsed, links: list[dict[str, Any]], a: dict[str, str],
        res: Callable[..., TurnResult],
    ) -> TurnResult:
        contacts = {str(c["id"]): c for c in self.core.contacts(uid)}
        cands = [
            (link, contacts[link["value"]]) for link in links if link["kind"] == "whatsapp" and link["value"] in contacts
        ]
        if not cands:
            return res(a["whatsapp_none"])
        named = [
            (link, c) for link, c in cands
            if any(
                name_matches(n, text) or (p.query and name_matches(n, p.query))
                for n in [*self._link_names(link), c["name"]]
            )
        ]
        if len(named) == 1:
            link, contact = named[0]
        elif not named and not p.query and len(cands) == 1:
            link, contact = cands[0]
        else:  # nobody named, or the name matches nobody: never guess
            return res(a["whatsapp_which"].format(names=", ".join(link["label"] for link, _ in cands)))
        digits = "".join(ch for ch in contact.get("phone", "") if ch.isdigit())
        if not digits:
            return res(a["whatsapp_no_number"].format(name=link["label"]))
        if len(digits) == 10:
            digits = "91" + digits  # an Indian mobile number without the country code
        return res(
            a["whatsapp_open"].format(name=link["label"]),
            {"type": "open", "kind": "whatsapp", "value": f"https://wa.me/{digits}", "title": link["label"],
             "contact_id": str(contact["id"])},
        )

    @staticmethod
    def _media_action(action: dict[str, Any], query: str) -> dict[str, Any]:
        """An open action carries the words she asked for too (a title for the screen, never a URL)."""
        return {**action, "query": query}

    def _open_media(
        self, uid: int, text: str, p: Parsed, links: list[dict[str, Any]], a: dict[str, str],
        res: Callable[..., TurnResult],
    ) -> TurnResult:
        """Play a named item directly, offer three cards for a category, ask one short question when the kind is
        unknown. The old generic "काय लावू?" and the "search results page" reply are gone: nothing claims to be
        playing when only a results page was opened."""
        kind = p.media_kind or media_kind(text)
        if p.topic == "news_video":
            kind = "news"
        query = p.query.strip() or media_topic(text)
        specific = bool(p.media_specific)

        if kind == "unknown":
            if query:  # a named thing after "what should I play?" is a video search, not "what kind?"
                kind = "video"
            else:
                # She only said "YouTube" / "a video" with no subject. If the family curated exactly one
                # YouTube favourite, open it; otherwise ask the one short question.
                favourites = [x for x in links if x["kind"] in _YT_MUSIC]
                if len(favourites) == 1:
                    return res(a["youtube_open"], self._media_action(self._open_link(favourites[0]), ""))
                self._media_ask[uid] = self._mono()  # the existing 2-minute "what should I play?" state
                return res(a["ask_media_kind"])
        if kind == "news":
            return self._offer_news(uid, text, links, a, res)

        # A family music row that covers what she asked is the best match: an explicitly named favourite
        # ("देवाची गाणी") or a category ("भजन", "गाणी"). A singer/song name the family did not save is searched.
        if query:
            family = [x for x in links if x["kind"] in _YT_MUSIC and covers(self._link_names(x), query)]
            if family:
                pick = family[0]
                if pick["kind"] == "youtube_query":
                    query = pick["value"]  # a saved search ("जुनी मराठी भजनं")
                else:
                    return res(a["play"], self._media_action(self._open_link(pick), query))

        if not query:  # a category with no words: search the category in Marathi
            query = {
                "music": "मराठी गाणी", "devotional": "मराठी भजन", "recipe": "मराठी रेसिपी",
                "exercise": "मराठी व्यायाम", "video": "मराठी व्हिडिओ",
            }.get(kind, "")
        query = self._with_marathi(query, specific)
        if not query:
            self._media_ask[uid] = self._mono()
            return res(a["ask_media_kind"])
        found = self._search(uid, query)
        if found is None:
            return self._results_page(query, a, res)
        if not found:
            return res(a["play_none"])
        items = [self._video_item(i, x) for i, x in enumerate(found)]
        if specific:
            return self._play_item(uid, items[0], a, res)
        return self._offer(uid, kind, query, items, a, res)

    def _offer_news(
        self, uid: int, text: str, links: list[dict[str, Any]], a: dict[str, str],
        res: Callable[..., TurnResult],
    ) -> TurnResult:
        """The family's approved news sources first (YouTube live / RSS, at most three cards); with none, live
        Marathi news from YouTube search. One approved source is played without asking."""
        sources = [x for x in links if x["kind"] in ("youtube_channel_live", "rss")]
        named = self._named_links(sources, text, "", ("youtube_channel_live", "rss"))
        if named:
            return self._play_news_link(uid, named[0], a, res)
        if len(sources) == 1:
            return self._play_news_link(uid, sources[0], a, res)
        if sources:
            items = [self._news_item(i, x) for i, x in enumerate(sources[:3])]
            return self._offer(uid, "news", "", items, a, res)
        found = self._search(uid, "", kind="news_video")
        if found is None:
            return self._results_page(_NEWS_SEARCH, a, res)
        if not found:
            return res(a["news_none"])
        items = [self._video_item(i, x) for i, x in enumerate(found)]
        return self._offer(uid, "news", "", items, a, res)

    @staticmethod
    def _with_marathi(query: str, specific: bool = False) -> str:
        """Search in Marathi for a category, but never change a named singer/song: "पुरणपोळी" -> "पुरणपोळी मराठी",
        while "भीमसेन जोशी भजन" is searched exactly as she said it."""
        q = " ".join(query.split())[:100]
        if specific or not q or "मराठी" in q:
            return q
        return f"{q} मराठी"

    def _search(self, uid: int, query: str, *, kind: str | None = None) -> list[dict[str, Any]] | None:
        """core-api search; None means "no key / quota / Google down", which opens the results page instead."""
        try:
            return self.core.youtube_search(uid, query, kind=kind)
        except CoreError as exc:
            if exc.status in (429, 502, 503):
                return None
            raise

    @staticmethod
    def _results_page(query: str, a: dict[str, str], res: Callable[..., TurnResult]) -> TurnResult:
        """No API key / quota: open YouTube's own results page, and say exactly that (never "playing")."""
        fallback = query or _NEWS_SEARCH
        url = "https://www.youtube.com/results?search_query=" + quote(fallback)
        return res(a["youtube_results"], {"type": "open", "kind": "url", "value": url, "title": fallback})

    @staticmethod
    def _video_item(index: int, video: dict[str, Any]) -> dict[str, Any]:
        return {
            "index": index + 1,
            "title": video["title"],
            "short": _short_title(video["title"], _CHOICE_TITLE_WORDS),
            "channel": video.get("channel", ""),
            "kind": "youtube_video",
            "value": video["video_id"],
            "video_id": video["video_id"],
        }

    @staticmethod
    def _news_item(index: int, link: dict[str, Any]) -> dict[str, Any]:
        return {
            "index": index + 1,
            "title": link["label"],
            "short": _short_title(link["label"], _CHOICE_TITLE_WORDS),
            "channel": "",
            "kind": link["kind"],
            "value": link["value"],
        }

    def _play_news_link(
        self, uid: int, link: dict[str, Any], a: dict[str, str], res: Callable[..., TurnResult],
    ) -> TurnResult:
        """A family YouTube live channel plays; an RSS feed is read aloud (opening the feed URL would show XML)."""
        if link["kind"] == "rss":
            return self._read_news(uid, a, res)
        return res(a["news_live"], self._media_action(self._open_link(link), ""))

    def _play_item(
        self, uid: int, item: dict[str, Any], a: dict[str, str], res: Callable[..., TurnResult],
    ) -> TurnResult:
        if item["kind"] == "rss":
            return self._read_news(uid, a, res)
        if item["kind"] in ("youtube_channel_live", "youtube_live"):
            return res(
                a["news_live"],
                {"type": "open", "kind": item["kind"], "value": item["value"], "title": item["title"]},
            )
        return res(
            a["play_found"].format(title=item["short"]),
            {"type": "open", "kind": "youtube_video", "video_id": item["value"], "title": item["title"]},
        )

    def _offer(
        self, uid: int, kind: str, query: str, items: list[dict[str, Any]], a: dict[str, str],
        res: Callable[..., TurnResult],
    ) -> TurnResult:
        """Three big cards and one short line. One item is played at once: a choice of one is not a choice."""
        if not items:
            return res(a["news_none"] if kind == "news" else a["play_none"])
        if len(items) == 1:
            return self._play_item(uid, items[0], a, res)
        self._media_choice[uid] = _MediaChoice(kind=kind, query=query, items=items, offset=0, at=self._mono())
        page = items[:3]
        return res(
            self._choice_line(page, a),
            {"type": "choice", "kind": "media", "value": "", "title": "", "query": query, "choices": page},
        )

    @staticmethod
    def _choice_line(page: list[dict[str, Any]], a: dict[str, str]) -> str:
        titles = [str(x.get("short") or x.get("title") or "व्हिडिओ") for x in page]
        if len(titles) >= 3:
            return a["choice_ask_three"].format(a=titles[0], b=titles[1], c=titles[2])
        return a["choice_ask_two"].format(a=titles[0], b=titles[1])

    # ---- the answer to the three cards ----------------------------------------------------------------------
    def _answer_choice(
        self, uid: int, text: str, lang: str, trace: dict[str, Any], t0: float,
        llm: dict[str, Any] | None = None,
    ) -> TurnResult | None:
        """A spoken / tapped answer to the cards, or None (the cards are cleared and the turn goes on normally).

        Safety, medicines and reminders never reach here: handle() checks them first and drops the cards.
        """
        state = self._media_choice.get(uid)
        if state is None:
            return None
        if self._mono() - state.at > _CHOICE_WINDOW_S:
            self._media_choice.pop(uid, None)
            return None
        a = A[rp.lang_or_default(lang)]
        norm = normalize(text)
        toks = tokens(norm)

        def out(line: str, action: dict[str, Any] | None = None) -> TurnResult:
            return TurnResult(
                line, OPEN_MEDIA, "care", lang, screen="reply", action=action or dict(NO_ACTION),
                trace=self._t({**trace, "intent": OPEN_MEDIA, "choice": True}, t0),
            )

        if self._is_choice_cancel(toks):
            self._media_choice.pop(uid, None)
            return out(a["choice_cancel"])
        if is_media_request(text):  # "भजन लाव" is a new request, not a card name
            self._media_choice.pop(uid, None)
            return None
        if self._is_choice_more(norm):
            page = self._next_page(state)
            if not page:
                return out(a["choice_none_more"])  # keep the cards she already has
            return out(
                self._choice_line(page, a),
                {"type": "choice", "kind": "media", "value": "", "title": "", "query": state.query,
                 "choices": page},
            )
        page = state.items[state.offset:state.offset + 3]
        index = self._llm_choice_index((llm or {}).get("slots") or {}, page)
        if index is None:
            index = self._ordinal(toks, len(page))
        if index is None:
            index = self._named_card(page, norm)
        if index is None:  # not an answer: the cards go, the sentence takes the normal path
            self._media_choice.pop(uid, None)
            return None
        item = page[index]
        self._media_choice.pop(uid, None)
        return self._play_item(uid, item, a, lambda line, action=None: out(line, action))  # type: ignore[arg-type]

    @staticmethod
    def _is_choice_more(norm: str) -> bool:
        padded = f" {norm} "
        return any(f" {p} " in padded for p in _CHOICE_MORE)

    @staticmethod
    def _is_choice_cancel(toks: list[str]) -> bool:
        return any(t in _CHOICE_CANCEL for t in toks)

    @staticmethod
    def _llm_choice_index(slots: dict[str, Any], page: list[dict[str, Any]]) -> int | None:
        """The card the LLM chose: an integer (1-based), a digit, an ordinal word, or a short title."""
        choice = slots.get("choice")
        if isinstance(choice, bool) or choice is None:
            return None
        if isinstance(choice, int):
            index = choice - 1
            return index if 0 <= index < len(page) else None
        text = normalize(str(choice))
        if not text:
            return None
        if text.isdigit():
            index = int(text) - 1
            return index if 0 <= index < len(page) else None
        for index, words in _CHOICE_ORDINALS.items():
            if index < len(page) and any(w in text.split() for w in words):
                return index
        for i, item in enumerate(page):
            title = normalize(str(item.get("short") or item.get("title") or ""))
            if title and (title in text or text in title):
                return i
        return None

    @staticmethod
    def _ordinal(toks: list[str], page_len: int) -> int | None:
        if any(t in _CHOICE_LAST for t in toks):
            return max(0, page_len - 1)
        for index, words in _CHOICE_ORDINALS.items():
            if index < page_len and any(t in words for t in toks):
                return index
        return None

    @staticmethod
    def _named_card(page: list[dict[str, Any]], norm: str) -> int | None:
        """A channel name or a distinctive title word ("ABP", "पुरणपोळी") picks that card. Generic words never do."""
        said = [t for t in tokens(norm) if len(t) >= 3 and t not in _CHOICE_STOP]
        if not said or len(tokens(norm)) > 6:
            return None
        matches = []
        for i, item in enumerate(page):
            words = [
                w for w in tokens(normalize(f"{item.get('title', '')} {item.get('channel', '')}"))
                if len(w) >= 3 and w not in _CHOICE_STOP
            ]
            if any(_same_word(s, w) for s in said for w in words):
                matches.append(i)
        return matches[0] if len(matches) == 1 else None

    def _next_page(self, state: _MediaChoice) -> list[dict[str, Any]]:
        nxt = state.offset + 3
        if nxt >= len(state.items):
            return []
        state.offset = nxt
        state.at = self._mono()  # the 2 minutes start again from the new cards
        return state.items[state.offset:state.offset + 3]

    def _open_reminders(self, uid: int) -> list[dict[str, Any]]:
        try:
            return [x for x in self.core.today(uid) if x["status"] != "done"]
        except (CoreError, httpx.HTTPError) as exc:
            log.warning("could not read today's reminders: %s", exc)
            return []

    def _names_an_open_reminder(self, uid: int, norm: str) -> bool:
        said = {w for w in norm.split(" ") if len(w) > 2 and w not in STOP}
        return any(
            said & {w for w in normalize(x["task"]).split(" ") if len(w) > 2 and w not in STOP}
            for x in self._open_reminders(uid)
        )

    def _single_open_reminder(self, uid: int) -> bool:
        return len(self._open_reminders(uid)) == 1

    def _dose_due(self, uid: int) -> bool:
        try:
            return bool(self.core.due_medicines(uid)["current"])
        except (CoreError, httpx.HTTPError):
            return False

    # intents whose wording must never reach the LLM as text (boundary 6: medicine words come only from SQL templates;
    # readings are numbers): the session keeps a neutral note that it happened, nothing she or Arjun said.
    _NOTE_ONLY = {
        "MED_TAKEN": "she said she took her medicine",
        "MED_SNOOZE": "she asked to be reminded about a medicine later",
        "MEDICAL_QUESTION": "she asked about a medicine; Arjun sent her to the family and doctor",
        "BP_READING": "she gave a health reading; it was noted for the family",
        "MEMORY_FORGOT": "she asked Arjun to forget something; it was forgotten",
    }

    def _record_turn(self, uid: int, said: str, res: TurnResult) -> None:
        """The ONE writer of session memory for a turn (rules, tools, safety, LLM, memory commands alike)."""
        now = self.clock()
        if res.intent in self._NOTE_ONLY:
            self.memory.event(uid, now, self._NOTE_ONLY[res.intent])
            return
        if res.intent in ("PENDING_REPEAT", "MEMORY_ASK"):
            self.memory.event(uid, now, "Arjun repeated a question that was still waiting")
            return
        if res.mode == "safety":
            kind = "emergency" if res.intent == "EMERGENCY" else "distress"
            self.memory.exchange(uid, now, said, res.reply, kind="safety", limit=_HISTORY_CARE_CHARS)
            self.memory.safety(uid, now, kind)
            return
        companion = res.mode == "companion"
        self.memory.exchange(
            uid, now, said, res.reply, kind="chat" if companion else "care", limit=0 if companion else _HISTORY_CARE_CHARS,
        )
        title = str(res.action.get("title") or "")
        if res.intent in ("OPEN_MEDIA", "NEWS_READ") and title:
            self.memory.event(uid, now, f"opened for her: {title[:80]}")
        elif res.action.get("type") == "control":
            self.memory.event(uid, now, f"media control: {res.action.get('value')}")
        elif res.intent in ("CREATE_REMINDER", "COMPLETE_REMINDER", "REQUEST_CAREGIVER", "CHECKIN_DONE", "CHECKIN_SKIPPED"):
            self.memory.event(uid, now, f"{res.intent.lower().replace('_', ' ')} done")

    @staticmethod
    def _answers_pending(intent: str, pending: dict[str, Any]) -> bool:
        if intent in _ANSWERS:
            return True
        if intent == "MED_SNOOZE" and pending["action_type"] == "MEDICINE_TAKEN":
            return True  # "later" is an answer to "did you take it?"
        return intent == "CREATE_REMINDER" and pending["action_type"] == "CREATE_REMINDER"  # a correction

    def _repeat_pending(
        self, uid: int, pending: dict[str, Any], lang: str, now: datetime, trace: dict[str, Any], t0: float
    ) -> TurnResult:
        """Anything that is not an answer, a cancel or a correction gets the SAME question again. The pending
        action is untouched: chat, a story offer or any new proposal never replaces it."""
        r = rp.R[rp.lang_or_default(lang)]
        payload = pending["payload"]
        kind = pending["action_type"]
        if kind == "MEDICINE_TAKEN":
            line = self._medicine_line(uid, payload.get("dose_id"), lang)
            if line:
                return TurnResult(
                    line, "PENDING_REPEAT", "care", lang, awaiting_confirmation=True, screen="confirm",
                    trace=self._t(trace, t0),
                )
        if kind == "CREATE_REMINDER" and payload.get("date") and payload.get("time"):
            when = f"{rp.say_date(payload['date'], now.date(), lang)} {rp.say_time(payload['time'], lang)}"
            question = r["confirm_reminder"].format(task=payload.get("task", ""), when=when)
        else:
            question = {
                "REQUEST_CAREGIVER": r["confirm_caregiver"],
                "SHARE_STORY": r["confirm_share"],
                "SAVE_STORY": r["ask_save_story"],
            }.get(kind, "")
        if r["yes_or_no"] not in question:
            question = f"{question} {r['yes_or_no']}".strip()
        return TurnResult(
            question, "PENDING_REPEAT", "care", lang, awaiting_confirmation=True, screen="confirm",
            trace=self._t(trace, t0),
        )

    # ------------------------------------------------------------------ T8: deliveries
    def _record_bp(
        self, uid: int, text: str, lang: str, trace: dict[str, Any], t0: float,
        llm: dict[str, Any] | None = None,
    ) -> TurnResult | None:
        """Store a spoken BP reading and repeat the same numbers back. Never a judgement, never advice."""
        numbers = parse_bp(text)
        slots = (llm or {}).get("slots") or {}
        bp = slots.get("bp")
        if numbers is None and isinstance(bp, dict):
            try:
                numbers = (int(bp["systolic"]), int(bp["diastolic"]))
            except (KeyError, TypeError, ValueError):
                numbers = None
        if numbers is None:
            return None
        systolic, diastolic = numbers
        try:
            self.core.add_bp_reading(uid, systolic, diastolic)
        except (CoreError, httpx.HTTPError) as exc:
            log.warning("could not store the BP reading: %s", exc)
            return None
        r = rp.R[rp.lang_or_default(lang)]
        return TurnResult(
            r["bp_recorded"].format(reading=format_bp(systolic, diastolic, lang)),
            "BP_READING", "care", lang, trace=self._t(trace, t0),
        )

    def _medicine_line(
        self, uid: int, dose_id: int | None, lang: str, key: str = "deliver_medicine"
    ) -> str | None:
        """The fixed medicine wording: name, dose and time exactly as the family entered them (from SQL)."""
        if dose_id is None:
            return None
        r = rp.R[rp.lang_or_default(lang)]
        for d in self.core.due_medicines(uid)["current"]:
            if d["id"] == dose_id:
                when = rp.say_time(d["due_at"][11:16], lang)
                return r[key].format(name=d["name"], dose=d["dose"], when=when)
        return None

    @staticmethod
    def _call_name(user: dict[str, Any]) -> str:
        """How Arjun addresses her: the family-set honorific, else her name without a "(synthetic)" tag."""
        return (user.get("honorific") or re.sub(r"\s*\([^)]*\)", "", user["name"])).strip()

    def _checkin_line(self, uid: int, kind: str, lang: str, attempt: int = 1, ref: str = "") -> str:
        """A fixed check-in prompt, filled only from SQL (her name, the interest, the contact, the appointment).
        A snack on a class day also names that class. A repeat (the follow-up) is the same question again."""
        r = rp.R[rp.lang_or_default(lang)]
        topic = topic_of(kind)
        prompt = r.get(f"checkin_prompt_{topic}") or r["checkin_prompt_breakfast"]
        if topic == "sleep":
            prompt = prompt.format(name=self._call_name(self.core.user(uid)))
        elif topic == "interest":
            prompt = prompt.format(interest=ref)
        elif topic == "home":
            prompt = prompt.format(name=ref.split("|", 1)[0])
        elif topic == "appt":
            at, _, title = ref.partition("|")
            prompt = prompt.format(when=rp.say_time(at, lang) if at else "", title=title)
        elif topic == "night":
            tomorrow = (local_now() + timedelta(days=1)).date()
            prompt = prompt.format(next=rp.say_weekday_date(tomorrow, lang)[0])
        if kind == "snack":
            event = self._evening_appointment(uid)
            if event is not None:
                prompt = (
                    f"{prompt} "
                    + r["checkin_class_today"].format(
                        when=rp.say_time(event["at"][11:16], lang), title=event["label"]
                    )
                )
        if attempt % 100 > 1:
            return r["checkin_again"].format(prompt=prompt)
        return prompt

    def _evening_appointment(self, uid: int) -> dict[str, Any] | None:
        """Today's evening appointment/class (from the day view), if the family set one."""
        try:
            day = self.core.day(uid)
        except (CoreError, httpx.HTTPError) as exc:
            log.warning("could not read today for the snack line: %s", exc)
            return None
        now = datetime.fromisoformat(day["now"])
        for item in day["items"]:
            if (
                item["kind"] == "appointment"
                and item["at"][:10] == now.date().isoformat()
                and int(item["at"][11:13]) >= 16
            ):
                return item
        return None

    def _read_checkin_answer(self, kind: str, text: str, llm_answer: str | None = None) -> str | None:
        """done / skipped: the word rules first, then ONE short strict-JSON LLM reading (3 s). "unclear" = None, and
        the sentence is then treated as ordinary talk. The LLM sees only this one answer; nothing it says is kept."""
        if llm_answer in ("done", "skipped"):
            return llm_answer
        answer = answer_for(kind, text)
        if answer is not None or self.evon is None or not hasattr(self.evon, "checkin_understanding"):
            return answer
        try:
            data = self.evon.checkin_understanding(  # type: ignore[attr-defined]
                topic_of(kind), text, timeout=min(_CHECKIN_UNDERSTAND_S, self._llm_remaining())
            )
        except Exception as exc:  # noqa: BLE001 - a slow or broken provider never breaks the turn
            log.info("check-in understanding failed: %s", type(exc).__name__)
            return None
        if not isinstance(data, dict) or data.get("topic") != topic_of(kind):
            return None
        return {"done": "done", "not_done": "skipped"}.get(str(data.get("status")))

    def _answer_open_checkin(
        self, uid: int, text: str, lang: str, trace: dict[str, Any], t0: float,
        llm: dict[str, Any] | None = None,
    ) -> TurnResult | None:
        """Record her done / skipped answer for the open check-in, on a fixed template, and say ONE short line.

        Safety wins: a health complaint or loneliness in the same sentence ("नाही, पोट दुखतंय") is not a check-in
        answer; it goes on to the symptom / loneliness flow, which also tells the family under the consent rules."""
        try:
            c = self.core.open_checkin(uid)
        except (CoreError, httpx.HTTPError) as exc:
            log.warning("could not read the open check-in: %s", exc)
            return None
        if not c or not c.get("heard"):
            return None  # queued but never spoken: the words are not an answer to it
        if symptom_category(text) or is_lonely(text):
            return None
        slots = (llm or {}).get("slots") or {}
        llm_answer = str(slots.get("checkin_answer") or "") or None
        answer = self._read_checkin_answer(c["kind"], text, llm_answer)
        if answer is None:
            return None
        try:
            self.core.answer_checkin(uid, c["id"], answer)
            self._context_cache.pop(uid, None)
        except CoreError as exc:
            log.warning("could not record the check-in answer: %s", exc)
            return None
        r = rp.R[rp.lang_or_default(lang)]
        topic = topic_of(c["kind"])
        ref = c.get("ref", "")
        if topic == "interest" and answer == "done" and ref:
            return self.handle(uid, f"{ref} लाव")  # yes -> the existing media flow takes over
        key = f"checkin_{answer}_{topic}"
        fill: dict[str, str] = {}
        if topic == "appt":
            at, _, title = ref.partition("|")
            fill = {"when": rp.say_time(at, lang) if at else "", "title": title}
        if topic == "home" and answer == "skipped":
            name, _, relation = ref.partition("|")
            fill = {"him": rp.pronoun_for(relation, lang)}
            self._family_offer[uid] = (self._mono(), name, relation)
        line = r.get(key, r["checkin_done_breakfast"]).format(**fill)
        intent = "CHECKIN_DONE" if answer == "done" else "CHECKIN_SKIPPED"
        return TurnResult(line, intent, "care", lang, trace=self._t(trace, t0))

    def _family_offer_answer(
        self, uid: int, text: str, lang: str, trace: dict[str, Any], t0: float,
        llm: dict[str, Any] | None = None,
    ) -> TurnResult | None:
        """Her reply to "त्याला निरोप पाठवू का?": yes sends the family the usual help message (with the undo window),
        no drops it. Anything else drops the offer and is handled as a normal sentence."""
        offer = self._family_offer.pop(uid, None)
        if offer is None or self._mono() - offer[0] > _OFFER_WINDOW_S:
            return None
        norm = normalize(text)
        r = rp.R[rp.lang_or_default(lang)]
        slots = (llm or {}).get("slots") or {}
        confirm = str(slots.get("confirm") or "").lower()
        if len(tokens(norm)) > 4 and confirm not in ("yes", "no"):
            return None
        if confirm == "no" or (not confirm and has_any(norm, NO)):
            return TurnResult(r["checkin_offer_no"], "CHECKIN_SKIPPED", "care", lang, trace=self._t(trace, t0))
        if confirm != "yes" and not has_any(norm, YES):
            return None
        message = r["checkin_offer_message"].format(name=offer[1])
        try:
            done = self._act(uid, "REQUEST_CAREGIVER", {"message": message})
        except (CoreError, httpx.HTTPError) as exc:
            log.warning("could not send the family message: %s", exc)
            return TurnResult(r["error"], "REQUEST_CAREGIVER", "care", lang, trace=self._t(trace, t0))
        if done is None:  # the old ask-first mode: one spoken yes still confirms it
            return TurnResult(
                r["confirm_caregiver"], "REQUEST_CAREGIVER", "care", lang, awaiting_confirmation=True,
                screen="confirm", trace=self._t(trace, t0),
            )
        return TurnResult(
            r["auto_caregiver"].format(family=self._family_obj(uid, lang)), "REQUEST_CAREGIVER", "care", lang,
            trace=self._t(trace, t0),
        )

    def _note_volunteered(self, uid: int, text: str, now: datetime) -> None:
        """She said she ate or walked without being asked: today's matching check-in is then answered, not asked."""
        found = volunteered_topic(text, now.hour)
        if found is None:
            return
        try:
            self.core.volunteer_checkin(uid, found[0], found[1])
        except (CoreError, httpx.HTTPError) as exc:
            log.warning("could not record the volunteered topic: %s", exc)

    def _check_in_is_busy(self, uid: int, media_playing: bool) -> bool:
        """The wrong moment for a question: media is playing, a safety flow is fresh, a yes/no waits, she spoke in the
        last 2 minutes, or a reminder / medicine prompt is being spoken right now."""
        if media_playing:
            return True
        last = self._last_turn.get(uid)
        if last is not None and self._mono() - last < _CHAT_QUIET_S:
            return True
        b = self.busy(uid)
        if b["pending"] or b["safety_hold"]:
            return True
        try:
            return any(d["status"] == "speaking" for d in self.core.open_deliveries(uid))
        except (CoreError, httpx.HTTPError):
            return True  # cannot tell: do not ask

    # ------------------------------------------------------------------ no-question mode
    def _act(self, uid: int, action_type: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Propose, then (no-question mode) confirm at once. core-api still validates everything: the LLM
        never writes. Returns the confirmed action, or None when the old ask-first mode wants a yes."""
        a = self.core.propose(uid, action_type, payload)
        if self.ask_first:
            return None
        try:
            done = self.core.confirm(uid, a["id"])
        except (CoreError, httpx.HTTPError):
            try:  # never leave a half-done proposal behind: no question is waiting for it in this mode
                self.core.reject(uid, a["id"])
            except (CoreError, httpx.HTTPError):
                pass
            raise
        self._last_done[uid] = (done, self._mono())
        self._context_cache.pop(uid, None)
        return done

    def _recent_done(self, uid: int) -> dict[str, Any] | None:
        hit = self._last_done.get(uid)
        if hit is None or self._mono() - hit[1] > config.UNDO_WINDOW_S:
            return None
        return hit[0]

    def _recent_dose(self, uid: int) -> int | None:
        hit = self._asked_dose.get(uid)
        if hit is None or self._mono() - hit[1] > 600:  # 10 min to say "घेतली"
            return None
        return hit[0]

    def note_activity(self, uid: int) -> None:
        """Tell core-api the elder just spoke (time only). Runs after the reply was sent; never raises."""
        try:
            self.core.mark_seen(uid, "voice")
        except (CoreError, httpx.HTTPError) as exc:
            log.warning("could not record activity for user %s: %s", uid, exc)

    def busy(self, uid: int) -> dict[str, Any]:
        """What stops a delivery or an idle close right now: a pending yes/no, a recent safety reply, a queue."""
        held = uid in self._last_safety and self._mono() - self._last_safety[uid] < _SAFETY_HOLD_S
        return {
            "pending": self.core.pending(uid) is not None,
            "safety_hold": bool(held),
            "queued": self.core.deliveries_waiting(uid),
        }

    def deliver_next(
        self, uid: int, session: str, media_playing: bool = False, call_active: bool = False
    ) -> dict[str, Any] | None:
        """Claim the next waiting reminder / medicine prompt and render its fixed wording, or return None.

        Never while a yes/no is pending or just after a safety reply. The claim is atomic in core-api, so two open
        sessions can never get the same item. Nothing is marked spoken here: the voice session does that after
        playback finished. No LLM is involved.
        """
        b = self.busy(uid)
        d = self.core.delivery_next(uid) if b["queued"] else None
        if d is not None and d["kind"] == "checkin" and (
            b["pending"] or b["safety_hold"] or call_active or self._check_in_is_busy(uid, media_playing)
        ):
            try:  # a question can wait: core-api asks again in 10 minutes (3 times at most); reminders never wait here
                self.core.postpone_checkin(uid, d["ref_id"])
            except (CoreError, httpx.HTTPError) as exc:
                log.warning("could not postpone check-in %s: %s", d["ref_id"], exc)
            return None
        if b["pending"] or b["safety_hold"] or call_active:
            return None
        if d is None:
            return None
        try:
            self.core.delivery_claim(uid, d["id"], session)
        except CoreError:
            return None  # another session got it, or it is no longer needed
        lang = rp.lang_or_default(self.core.user(uid)["language"])
        r = rp.R[lang]
        try:
            if d["kind"] == "medicine":
                text = self._medicine_line(uid, d["ref_id"], lang)
                if text is None:
                    raise CoreError(409, "dose is not open")
                if self.ask_first:
                    self.core.propose(  # one spoken yes confirms it
                        uid, "MEDICINE_TAKEN", {"dose_id": d["ref_id"], "asked": "delivery"}
                    )
                    screen, item, ask = "medicine", f"dose:{d['ref_id']}", True
                else:  # announced only; "घेतली" / "हो" in the next minutes records it, "नाही" too
                    text = self._medicine_line(uid, d["ref_id"], lang, key="deliver_medicine_auto") or text
                    self._asked_dose[uid] = (d["ref_id"], self._mono())
                    screen, item, ask = "medicine", f"dose:{d['ref_id']}", False
            elif d["kind"] == "checkin":
                text = self._checkin_line(uid, d["label"], lang, d["attempt"], d.get("detail", ""))
                screen, item, ask = "reply", f"checkin:{d['ref_id']}", False
            else:
                when = rp.say_time(d["due_at"][11:16], lang)
                key = "deliver_reminder_late" if d["late"] else "deliver_reminder"
                text = r[key].format(task=d["label"], when=when)
                screen, item, ask = "reminder", f"reminder:{d['ref_id']}", False
        except (CoreError, httpx.HTTPError) as exc:
            log.warning("could not render delivery %s: %s", d["id"], exc)
            self.core.delivery_release(uid, d["id"], session, "interrupted")
            return None
        self._delivered[d["id"]] = (uid, text, d["kind"])  # recorded in the session once it was really SPOKEN
        return {
            "delivery_id": d["id"], "kind": d["kind"], "text": text, "screen": screen, "item": item,
            "awaiting_confirmation": ask, "language": lang,
        }

    def deliver_spoken(self, uid: int, delivery_id: int, session: str) -> None:
        self.core.delivery_spoken(uid, delivery_id, session)
        said = self._delivered.pop(delivery_id, None)
        if said is None:
            return
        _, text, kind = said
        now = self.clock()
        if kind == "medicine":  # name and dose come only from SQL: the session keeps a neutral note, not the words
            self.memory.event(uid, now, "Arjun reminded her about a medicine (wording not kept)")
        else:  # a check-in question or a reminder Arjun said on his own: the open question waits for her answer
            self.memory.arjun_said(uid, now, text, "checkin" if kind == "checkin" else "reminder")

    def deliver_release(self, uid: int, delivery_id: int, session: str, reason: str) -> None:
        self._delivered.pop(delivery_id, None)
        self.core.delivery_release(uid, delivery_id, session, reason)

    def opener(self, user_id: int) -> str | None:
        """Proactive 'Shikva na' opener - scheduler-triggered, gated by caregiver-set hours."""
        user = self.core.user(user_id)
        if not self.core.opener_allowed(user_id) or not user["interests"]:
            return None
        lang = rp.lang_or_default((user.get("preferred_languages") or [user["language"]])[0])
        now = self.clock()
        followup = self._yesterday_followup(user_id, now, refresh=True)
        if followup and self.evon is not None and hasattr(self.evon, "companion_reply"):
            try:
                raw = self.evon.companion_reply(
                    "नमस्कार", lang, now, interests=user.get("interests") or [],
                    context=self._base_context(user_id, now, user) +
                    "\nFIRST GREETING FOLLOW-UP: warmly ask how this one item from yesterday went; do not invent details: " + followup,
                    timeout=config.LLM_TIMEOUT_S,
                )
                clean, _ = split_voice_tags(raw)
                safe, _ = sanitize_companion(clean, lang)
                if safe:
                    return safe
            except Exception as exc:  # noqa: BLE001 - the rules opener remains the timeout/error fallback
                log.info("opener follow-up failed: %s", type(exc).__name__)
        interest = user["interests"][0]
        return rp.R[lang]["opener"].format(name=user["name"], interest=interest)

    # ------------------------------------------------------------------ intent
    def _intent(
        self,
        text: str,
        profile: Profile,
        now: datetime,
        lang: str,
        has_pending: bool,
        draft: Draft | None,
        pending_action: str | None = None,
        conversing: bool = False,
        llm: dict[str, Any] | None = None,
        llm_attempted: bool = False,
    ) -> tuple[Parsed, str]:
        rules = parse(text, profile, now, lang, has_pending, pending_action)
        # A health complaint is never an answer to an open question. "आज माझी तब्येत बरी नाही" used to end in
        # "नाही" -> CONFIRM_NO -> cancel the pending reminder and say the family was told help is not needed.
        # The medicine question is the one exception: "नाही, घेतली नाही" must still record a missed dose.
        if (
            rules.intent == "CONFIRM_NO"
            and pending_action != "MEDICINE_TAKEN"
            and symptom_category(text)
        ):
            rules.intent = "SYMPTOM"
        # A yes/no is an ANSWER only when it looks like one ("हो", "नको", "नाही, नको"). A declarative sentence
        # that merely contains a negation is not: "माझा चस्मा सापडत नाही" used to undo the last action and say
        # "घरच्यांना कळवलं की आता मदत नको". The LLM reads those; the rules only answer the short forms.
        if (
            rules.intent in ("CONFIRM_YES", "CONFIRM_NO", "DECLINE_TOPIC")
            and pending_action != "MEDICINE_TAKEN"
            and rules.topic != "correction"  # "… दहा डॉक्टरांकडे नाही जायचं" corrects the pending reminder
            and not _looks_like_an_answer(text)
        ):
            rules.intent = "UNKNOWN"
        if pending_action == "MEDICINE_TAKEN":  # the open question is "did you take it?"
            norm = normalize(text)
            if rules.intent in ("COMPLETE_REMINDER", "MED_TAKEN") and has_any(norm, MED_TAKEN_WORDS):
                rules.intent = "CONFIRM_YES"  # "घेतली" answers it
            elif rules.intent in ("UNKNOWN", "CHAT") and has_any(norm, SNOOZE_WORDS):
                rules.intent = "MED_SNOOZE"  # "नंतर" / "later" answers it
        # A medicine question is always deflected, whatever the LLM thinks it is.
        if rules.intent == "MEDICAL_QUESTION":
            return rules, "rules"
        # In slot-filling, short answers ("udya", "sakali") complete the open reminder draft.
        if draft is not None and rules.intent in ("UNKNOWN", "CHAT", "CREATE_REMINDER"):
            rules.intent = "CREATE_REMINDER"
            return rules, "rules"
        # Deterministic state answers (yes/no, stop, confirmations, greetings) stay on the rules. They are
        # state, not language understanding; the LLM call still happened and its slots were used above.
        deterministic = (
            "CONFIRM_YES", "CONFIRM_NO", "DECLINE_TOPIC", "FORGET_MEMORY", "MED_TAKEN", "MED_SNOOZE",
            "TIME_QUERY", "NEXT_UP", "GREETING", "HEARING_CHECK", "VIDEO_CALL", "CALL_FAMILY_REMINDER",
        )
        if llm is not None and rules.intent not in deterministic:
            parsed = self._parsed_from_llm(llm, rules, lang)
            if parsed is not None:
                return parsed, "llm"
        if rules.intent == "UNKNOWN" and symptom_category(text):
            return rules, "rules"  # a health complaint the LLM could not read still gets the fixed template
        if llm_attempted:
            return rules, "rules"  # already asked this turn; never a second intent call
        # Legacy provider without `understand_turn`: the old path, only for turns the rules cannot read.
        if (
            self.evon is None
            or has_pending
            or rules.intent != "UNKNOWN"
            or self._llm_remaining() < _MIN_LLM_BUDGET_S
        ):
            return rules, "rules"
        data = self.evon.extract_intent(
            text, lang, now, profile.wake_time, profile.lunch_time, profile.dinner_time,
            timeout=self._llm_remaining(),
        )
        if data is None:
            return rules, "rules"
        intent = data["intent"]
        if intent not in _LLM_INTENTS:  # it may suggest only these; everything else stays "not understood"
            return rules, "rules"
        if intent == "CREATE_REMINDER":
            d = Draft(task=data.get("task") or None, date=data.get("date") or None)
            if data.get("time_ambiguous") or not data.get("time"):
                # keep AM/PM unresolved: let the rule parser find the raw hour if it can
                d.time = None
                if rules.draft.ambiguous_hour:
                    d.ambiguous_hour = rules.draft.ambiguous_hour
                elif rules.draft.time:
                    d.time = rules.draft.time
            else:
                d.time = data["time"]
            return Parsed(intent, float(data["confidence"]), lang, d), "llm"
        if intent in APP_INTENTS:  # only a spoken name or a control word; the link itself comes from the family's rows
            topic = data.get("media_control") if intent == MEDIA_CONTROL else rules.topic
            query = (data.get("link_label") or data.get("media_query") or "") if intent != MEDIA_CONTROL else ""
            query = str(query)
            if "http" in query.lower():  # the model may never turn her words into a URL
                query = ""
            return Parsed(intent, float(data["confidence"]), lang, rules.draft, topic=topic, query=query[:100]), "llm"
        return (
            Parsed(intent, float(data["confidence"]), lang, rules.draft, rules.contact_hint, rules.topic),
            "llm",
        )

    def _parsed_from_llm(
        self, data: dict[str, Any], rules: Parsed, lang: str
    ) -> Parsed | None:
        """Translate the unified JSON intent + slots into the internal Parsed the dispatcher already speaks.

        `legacy_reply` (a provider that ignored the JSON contract and wrote prose) may only speak; it never
        overrides a clear rule action such as a reminder, a medicine report or an app command.
        """
        intent = str(data.get("intent") or "")
        slots = data.get("slots") if isinstance(data.get("slots"), dict) else {}
        try:
            confidence = float(data.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if data.get("legacy_reply") and rules.intent not in ("CHAT", "UNKNOWN"):
            return None
        confirm = str(slots.get("confirm") or "").lower()
        if confirm in ("yes", "no"):
            return Parsed("CONFIRM_YES" if confirm == "yes" else "CONFIRM_NO", confidence, lang, rules.draft)
        query = str(slots.get("query") or slots.get("contact") or "")
        if "http" in query.lower():
            query = ""
        kind = str(slots.get("media_kind") or "")
        # An old intent-only JSON from a fake/legacy provider keeps its exact meaning. OPEN_LINK and
        # OPEN_WHATSAPP must not become a media search, and a control word is not a topic decline.
        legacy_intent = str(data.get("legacy_intent") or "")
        if legacy_intent == "OPEN_LINK":
            return Parsed("OPEN_LINK", confidence, lang, rules.draft, query=query[:100])
        if legacy_intent == "OPEN_WHATSAPP":
            return Parsed("OPEN_WHATSAPP", confidence, lang, rules.draft, contact_hint=query or rules.contact_hint)
        if legacy_intent == "MEDIA_CONTROL":
            control = str(slots.get("control") or "")
            return Parsed(MEDIA_CONTROL, confidence, lang, rules.draft, topic=control or rules.topic)
        if legacy_intent == "MED_SNOOZE":
            return Parsed("MED_SNOOZE", confidence, lang, rules.draft)
        if legacy_intent in ("TIME_QUERY", "NEXT_UP"):
            return Parsed(legacy_intent, confidence, lang, rules.draft, topic=rules.topic)
        if intent == "chat":
            return Parsed("CHAT", confidence, lang, rules.draft, rules.contact_hint, rules.topic)
        if intent == "unclear":
            return Parsed("UNKNOWN", confidence, lang, rules.draft)
        if intent == "reminder_add":
            d = Draft(task=slots.get("task") or rules.draft.task, date=slots.get("date") or rules.draft.date)
            if slots.get("time_ambiguous") or not slots.get("time"):
                if rules.draft.ambiguous_hour:
                    d.ambiguous_hour = rules.draft.ambiguous_hour
                elif rules.draft.time:
                    d.time = rules.draft.time
            else:
                d.time = str(slots["time"])
            return Parsed("CREATE_REMINDER", confidence, lang, d)
        if intent == "reminder_done":
            return Parsed("COMPLETE_REMINDER", confidence, lang, rules.draft, topic=rules.topic)
        if intent == "medicine_taken":
            return Parsed("MED_TAKEN", confidence, lang, rules.draft)
        if intent == "medicine_query":
            return Parsed("MEDICAL_QUESTION", confidence, lang, rules.draft)
        if intent == "media":
            topic = "news_video" if kind == "news" else (kind or rules.media_kind)
            p = Parsed(
                OPEN_MEDIA, confidence, lang, rules.draft, topic=topic, query=query[:100],
                media_kind=kind or rules.media_kind, media_specific=bool(slots.get("media_specific") or rules.media_specific),
            )
            return p
        if intent == "news":
            return Parsed(NEWS_READ, confidence, lang, rules.draft)
        if intent == "call_family":
            return Parsed("CALL_FAMILY_REMINDER", confidence, lang, rules.draft, contact_hint=query or rules.contact_hint)
        if intent == "video_call":
            return Parsed("VIDEO_CALL", confidence, lang, contact_hint=query or rules.contact_hint)
        if intent == "message_family":
            return Parsed("REQUEST_CAREGIVER", confidence, lang, rules.draft, contact_hint=query or rules.contact_hint)
        if intent == "today_query":
            p = Parsed("LIST_TODAY", confidence, lang, rules.draft)
            p.topic = rules.topic
            return p
        if intent == "undo":
            return Parsed("CONFIRM_NO", confidence, lang, rules.draft)
        if intent == "stop":
            control = str(slots.get("control") or "")
            if control in CONTROLS or rules.intent == MEDIA_CONTROL:
                return Parsed(MEDIA_CONTROL, confidence, lang, rules.draft, topic=control or rules.topic)
            return Parsed("DECLINE_TOPIC", confidence, lang, rules.draft)
        if intent == "health_complaint":
            return Parsed("SYMPTOM", confidence, lang, rules.draft)
        return None


    # ------------------------------------------------------------------ dispatch
    def _dispatch(
        self,
        uid: int,
        text: str,
        p: Parsed,
        pending: dict[str, Any] | None,
        draft: Draft | None,
        profile: Profile,
        now: datetime,
        lang: str,
        llm: dict[str, Any] | None = None,
    ) -> TurnResult:
        r = rp.R[rp.lang_or_default(lang)]
        intent = p.intent

        def out(msg: str, mode: str = "care", wait: bool = False) -> TurnResult:
            return TurnResult(
                msg, intent, mode, lang, awaiting_confirmation=wait,
                screen="confirm" if wait else ("story" if mode == "companion" else "reply"),
            )

        if not self.ask_first and pending is None and draft is None:
            if intent == "CONFIRM_NO":
                recent = self._recent_done(uid)
                if recent is not None:  # "नको / चुकलं" right after Arjun did something: put it back
                    self._last_done.pop(uid, None)
                    try:
                        self.core.undo(uid, recent["id"])
                    except CoreError as exc:
                        log.warning("undo failed: %s", exc)
                        return out(r["error"])
                    if recent["action_type"] == "REQUEST_CAREGIVER":
                        return out(r["undone_help"])
                    return out(r["undone_retry"] if p.topic == "correction" else r["undone"])
                dose = self._recent_dose(uid)
                if dose is not None:  # "नाही" to a medicine prompt: not taken (self-reported), family told
                    self._asked_dose.pop(uid, None)
                    try:
                        a = self.core.propose(uid, "MEDICINE_TAKEN", {"dose_id": dose, "asked": "delivery"})
                        self.core.reject(uid, a["id"], answered_no=True)
                    except CoreError as exc:
                        log.warning("not-taken record failed: %s", exc)
                    return out(r["med_not_taken_ack"])
            if intent == "CONFIRM_YES":
                dose = self._recent_dose(uid)
                if dose is not None:
                    self._asked_dose.pop(uid, None)
                    return self._medicine_action(uid, text, "MED_TAKEN", lang, out, dose_id=dose)
                if self._recent_done(uid) is not None:
                    return out(r["ok_ack"])

        # "nako" with nothing to refuse is a topic decline, not a cancellation
        if intent == "CONFIRM_NO" and pending is None and draft is None:
            intent = "DECLINE_TOPIC"

        # Answered in place: an open reminder draft or pending yes/no is left exactly as it was.
        if intent == "GREETING":
            # She has told Arjun things before (facts, or earlier talk today): greet like someone who remembers, and follow
            # up on an event she mentioned. With nothing to remember, or no LLM, the fixed greeting stays.
            followup = self._yesterday_followup(uid, now)
            if self.evon is not None and (followup or self.facts.all(uid) or self.memory.view(uid, now).messages):
                reply, speech, from_llm = self._chat_reply(
                    uid, text, lang, now, llm_reply=str((llm or {}).get("reply") or ""), opener_followup=followup
                )
                if from_llm:
                    res = out(reply, "companion")
                    res.speech = speech
                    res.source = "llm"
                    return res
            return out(r["greet"])
        if intent == "HEARING_CHECK":
            return out(r["hearing_ok"])

        if intent == "CONFIRM_YES":
            if pending is None:
                return out(r["nothing_pending"])
            done = self.core.confirm(uid, pending["id"])
            key = {
                "CREATE_REMINDER": "reminder_saved",
                "COMPLETE_REMINDER": "completed",
                "REQUEST_CAREGIVER": "caregiver_done",
                "SHARE_STORY": "shared_done",
                "SAVE_STORY": "story_saved",
                "MEDICINE_TAKEN": "med_taken_done",
                "MEDICINE_SNOOZE": "med_snoozed_done",
            }[done["action_type"]]
            mode = "companion" if done["action_type"] in ("SHARE_STORY", "SAVE_STORY") else "care"
            saved = out(r[key], mode)
            saved.screen = "saved"
            return saved

        if intent == "CONFIRM_NO":
            asked_taken = pending is not None and pending["payload"].get("asked") == "delivery"
            if pending is not None and asked_taken and p.topic != "correction":
                self.core.reject(uid, pending["id"], answered_no=True)  # recorded as not taken (self-reported)
                self._drafts.pop(uid, None)
                return out(r["med_not_taken_ack"])  # no advice, no "take it later", no repeat
            if pending is not None:
                self.core.reject(uid, pending["id"])
            self._drafts.pop(uid, None)
            return out(r["cancelled_retry"] if p.topic == "correction" else r["cancelled"])

        if intent == "DECLINE_TOPIC":
            self._drafts.pop(uid, None)
            if pending is not None:
                self.core.reject(uid, pending["id"])
            self.core.decline(uid)  # ends proactive openers for the day; no re-ask
            self._convo_at.pop(uid, None)
            return out(r["decline"], "companion")

        # Any non-reminder intent abandons an open reminder draft and stale confirmation.
        if intent != "CREATE_REMINDER":
            self._drafts.pop(uid, None)

        if intent in APP_INTENTS:
            return self._app_command(uid, text, p, lang)

        if intent == "CREATE_REMINDER":
            return self._create_reminder(uid, text, p, draft, profile, now, lang, out)

        if intent == "LIST_TODAY":
            if p.topic == "ambiguous":  # "उद्या आज काय आहे": never guess which day
                return out(r["ask_date"])
            today = now.date().isoformat()
            on = p.topic if p.topic and p.topic != today else None  # another day, read from SQL
            rows = [
                x for x in self.core.day(uid, on)["items"]
                if x["kind"] in ("reminder", "appointment", "medicine")
                and x["status"] not in ("done", "taken", "unconfirmed")
            ]
            when = rp.say_date(on, now.date(), lang) if on else ""
            if not rows:
                return out(r["day_none"].format(when=when) if on else r["today_none"])
            items = "; ".join(
                f"{rp.say_time(x['at'][11:16], lang)} {rp.item_text(x, lang)}" for x in rows
            )
            return out(r["day_list"].format(when=when, items=items) if on else r["today_list"].format(items=items))

        if intent in ("TIME_QUERY", "NEXT_UP"):
            return self._time_guidance(uid, intent, p, lang, out)

        if intent == "GET_APPOINTMENT":
            appt = self.core.next_appointment(uid)
            if not appt:
                return out(r["appt_none"])
            when = (
                f"{rp.say_date(appt['starts_at'][:10], now.date(), lang)} "
                f"{rp.say_time(appt['starts_at'][11:16], lang)}"
            )
            place = f", {appt['location']}" if appt.get("location") else ""
            return out(r["appt_next"].format(title=appt["title"], when=when, place=place))

        if intent == "VIDEO_CALL":
            contacts = self.core.contacts(uid)
            eligible = [c for c in contacts if not any(w in (c.get("relation") or "").casefold()
                                                         for w in ("doctor", "dr.", "डॉक", "वैद्य"))]
            named = [c for c in eligible if name_matches(c["name"], text)
                     or (p.contact_hint and name_matches(c["name"], p.contact_hint))]
            chosen = named[0] if named else next(
                (c for c in eligible if "son" in (c.get("relation") or "").casefold()
                 or "मुलग" in (c.get("relation") or "")),
                eligible[0] if eligible else None,
            )
            if chosen is None:
                return out(r["no_contacts"])
            return TurnResult(
                f"{chosen['name']}ला व्हिडिओ कॉल लावतो, थांबा.", "VIDEO_CALL", "care", lang,
                action={"type": "call", "kind": "video", "value": str(chosen["id"]),
                        "contact_id": str(chosen["id"]), "title": chosen["name"]},
            )

        if intent == "CALL_FAMILY_REMINDER":
            contacts = self.core.contacts(uid)
            if not contacts:
                return out(r["no_contacts"])
            norm = normalize(text)
            named = [c for c in contacts if normalize(c["name"]).split(" ")[0] in norm.split(" ")]
            if len(named) == 1:
                return out(r["call_family"].format(name=named[0]["name"]))
            if len(contacts) == 1:
                return out(r["call_family"].format(name=contacts[0]["name"]))
            names = ", ".join(c["name"] for c in contacts)
            return out(r["ask_contact"].format(names=names))

        if intent == "REQUEST_CAREGIVER":
            if self._act(uid, "REQUEST_CAREGIVER", {"message": "Please call me."}) is None:
                return out(r["confirm_caregiver"], wait=True)
            return out(r["auto_caregiver"].format(family=self._family_obj(uid, lang)))

        # A bare "ghetli" while a medicine is due is the medicine, not a reminder.
        if intent == "COMPLETE_REMINDER" and has_any(normalize(text), MED_TAKEN_WORDS):
            if self.core.due_medicines(uid)["current"]:
                intent = "MED_TAKEN"

        if intent == "COMPLETE_REMINDER":
            return self._complete(uid, text, lang, out)

        if intent == "MED_TAKEN" and not self.core.due_medicines(uid)["current"]:
            # No family-set medicine is due: "tablet ghetli" may close an older plain reminder.
            if any(x["status"] != "done" for x in self.core.today(uid)):
                intent = "COMPLETE_REMINDER"
                return self._complete(uid, text, lang, out)

        if intent in ("MED_TAKEN", "MED_SNOOZE"):
            return self._medicine_action(uid, text, intent, lang, out)

        if intent == "MEDICAL_QUESTION":
            return self._deflect_medical(uid, "med_deflect", lang, out)

        if intent == "SHARE_STORY_WITH_FAMILY":
            story = self.core.latest_story(uid)
            if not story:
                return out(r["no_story"], "companion")
            if self._act(uid, "SHARE_STORY", {"story_id": story["id"]}) is None:
                return out(r["confirm_share"], "companion", wait=True)
            return out(r["auto_share"], "companion")

        if intent == "FORGET_MEMORY":
            if pending is not None and pending["action_type"] == "SAVE_STORY":
                self.core.reject(uid, pending["id"])  # discard the unsaved story
                return out(r["forgotten"], "companion")
            story = self.core.latest_story(uid)
            if not story:
                return out(r["no_story"], "companion")
            self.core.delete_story(uid, story["id"])
            return out(r["forgotten"], "companion")

        if intent in ("CHAT", "UNKNOWN"):
            # "keep your story?" is a companion-mode offer only: never over a pending question or an open
            # reminder draft, and never for recognizer junk (very few distinct words).
            words = text.split()
            real_story = len(words) >= config.LONG_STORY_WORDS and len({normalize(w) for w in words}) / len(words) >= 0.4
            if real_story and pending is None and draft is None:
                if self.ask_first:
                    self.core.propose(uid, "SAVE_STORY", {"summary": text.strip()[:2000]})
                    return out(r["ask_save_story"], "companion", wait=True)
                # No question: kept privately (only she can share it: "हे घरच्यांना सांग"); the chat goes on.
                before = self._last_done.get(uid)
                self._act(uid, "SAVE_STORY", {"summary": text.strip()[:2000]})
                # Nothing was read back to her, so there is nothing for "नाही" to undo: a bare no after a long story
                # answers the chat, it must not delete the story (found 2026-10-31 in the 15-turn measurement run).
                if before is None:
                    self._last_done.pop(uid, None)
                else:
                    self._last_done[uid] = before
            reply, speech, from_llm = self._chat_reply(
                uid, text, lang, now, llm_reply=(llm or {}).get("reply") or ""
            )
            res = out(reply, "companion")
            res.speech = speech
            res.silent = not bool(reply)
            if from_llm:
                res.source = "llm"
            return res

        reply = self._specific_clarification(uid, text, lang)
        result = out(reply, "companion")
        result.silent = not bool(reply)
        return result

    # ------------------------------------------------------------------ helpers
    def _create_reminder(
        self,
        uid: int,
        text: str,
        p: Parsed,
        draft: Draft | None,
        profile: Profile,
        now: datetime,
        lang: str,
        out: Callable[..., TurnResult],
    ) -> TurnResult:
        r = rp.R[rp.lang_or_default(lang)]
        if draft is None:
            d = p.draft
        else:  # follow-up answer: merge new slots into the open draft
            d = apply_text(draft, text, profile, now, is_followup=True)
        # Medicines are set by the family on the dashboard, never by voice.
        if (d.task and has_med_word(normalize(d.task))) or has_med_word(normalize(text)):
            self._drafts.pop(uid, None)
            return self._deflect_medical(uid, "med_family_sets", lang, out)
        self._drafts[uid] = d

        missing = d.missing()
        if missing == "task":
            return out(r["ask_task"], wait=True)
        if missing == "date":
            return out(r["ask_date"], wait=True)
        if missing == "ampm" and d.ambiguous_hour:
            return out(r["ask_ampm"].format(hour=d.ambiguous_hour[0]), wait=True)
        if missing == "meal":
            return out(r["ask_meal"], wait=True)
        if missing == "time":
            return out(r["ask_time"], wait=True)

        assert d.task and d.date and d.time
        recent = self._recent_done(uid)
        if (
            not self.ask_first and recent is not None and recent["action_type"] == "CREATE_REMINDER"
            and has_any(normalize(text), NO)
        ):  # "नाही, अकरा वाजता ठेव": the new one replaces the one just saved
            self._last_done.pop(uid, None)
            try:
                self.core.undo(uid, recent["id"])
            except CoreError as exc:
                log.warning("undo before correction failed: %s", exc)
        try:
            done = self._act(
                uid,
                "CREATE_REMINDER",
                {"task": d.task, "date": d.date, "time": d.time, "time_ambiguous": False},
            )
        except CoreError as exc:
            if exc.status == 422:  # e.g. time already passed - keep task/date, re-ask time
                d.time = None
                return out(r["time_passed"], wait=True)
            raise
        self._drafts.pop(uid, None)
        when = f"{rp.say_date(d.date, now.date(), lang)} {rp.say_time(d.time, lang)}"
        if done is None:
            return out(r["confirm_reminder"].format(task=d.task, when=when), wait=True)
        res = out(r["auto_reminder"].format(task=d.task, when=when))
        res.screen = "saved"
        return res

    def _complete(
        self, uid: int, text: str, lang: str, out: Callable[..., TurnResult]
    ) -> TurnResult:
        r = rp.R[rp.lang_or_default(lang)]
        open_rows = [x for x in self.core.today(uid) if x["status"] != "done"]
        if not open_rows:
            return out(r["none_to_complete"])
        said = set(normalize(text).split(" "))
        matches = [x for x in open_rows if said & set(normalize(x["task"]).split(" "))]
        if len(matches) == 1:
            target = matches[0]
        elif not matches and len(open_rows) == 1:
            target = open_rows[0]  # still verified by a spoken yes/no below
        else:
            items = ", ".join(x["task"] for x in (matches or open_rows))
            return out(r["which_reminder"].format(items=items))
        if self._act(uid, "COMPLETE_REMINDER", {"reminder_id": target["id"]}) is None:
            return out(r["confirm_complete"].format(task=target["task"]), wait=True)
        res = out(r["auto_complete"].format(task=target["task"]))
        res.screen = "saved"
        return res

    def _day(self, uid: int) -> dict[str, Any]:
        return self.core.day(uid)

    def _time_guidance(
        self, uid: int, intent: str, p: Parsed, lang: str, out: Callable[..., TurnResult]
    ) -> TurnResult:
        """Say the time/date from the household clock, then what is pending and what is next.

        Fixed templates over SQL rows only - no model-generated advice about what to do.
        """
        r = rp.R[rp.lang_or_default(lang)]
        day = self._day(uid)
        now = datetime.fromisoformat(day["now"])
        parts: list[str] = []
        if intent == "TIME_QUERY":
            if p.topic == "date":
                wd, d, mo = rp.say_weekday_date(now.date(), lang)
                parts.append(r["date_now"].format(weekday=wd, day=d, month=mo))
            else:
                parts.append(r["time_now"].format(clock=rp.say_clock(now.strftime("%H:%M"), lang)))
        if intent == "NEXT_UP" and day["open_now"]:
            items = "; ".join(rp.item_text(x, lang) for x in day["open_now"])
            parts.append(r["open_now"].format(items=items))
        nxt = day.get("next")
        if nxt:
            when = rp.say_time(nxt["at"][11:16], lang)
            parts.append(r["next_up"].format(when=when, label=rp.item_text(nxt, lang)))
        elif not (intent == "NEXT_UP" and day["open_now"]):
            parts.append(r["next_none"])
        return out(" ".join(parts))

    def briefing(self, uid: int) -> str | None:
        """Morning/day briefing text for the scheduler. None before the family-set wake time."""
        user = self.core.user(uid)
        day = self._day(uid)
        now = datetime.fromisoformat(day["now"])
        if now.strftime("%H:%M") < user["wake_time"]:
            return None
        lang = rp.lang_or_default(user["language"])
        r = rp.R[lang]
        # What is still ahead today, plus anything already due and unfinished. A briefing that
        # lists lunch at 1 pm to someone listening at 4 pm would be wrong guidance.
        rows = [
            x for x in day["items"]
            if x["kind"] != "wake"
            and x["status"] not in ("done", "taken", "unconfirmed")
            and (x["at"] > day["now"] or x in day["open_now"])
        ]
        greeting = rp.greeting(now.hour, lang)
        if not rows:
            return r["briefing_none"].format(greeting=greeting)
        items = "; ".join(f"{rp.say_time(x['at'][11:16], lang)} {rp.item_text(x, lang)}" for x in rows)
        return r["briefing"].format(greeting=greeting, items=items)

    def _deflect_medical(
        self, uid: int, key: str, lang: str, out: Callable[..., TurnResult]
    ) -> TurnResult:
        """Fixed template only: no medical content. The family gets told only after a spoken yes."""
        r = rp.R[rp.lang_or_default(lang)]
        contacts = self.core.contacts(uid)
        try:  # her name as the family knows it, not a fixed "Aaji"
            user = self.core.user(uid)
            who = (str(user.get("address_as") or "").strip()
                   or str(user.get("name") or "").replace("(synthetic)", "").strip() or "She")
        except (CoreError, httpx.HTTPError):
            who = "She"
        message = (
            f"{who} asked to set a medicine time. Please add it on the dashboard."
            if key == "med_family_sets"
            else f"{who} has a question about medicine. Please call her; Arjun did not answer it."
        )
        if self._act(uid, "REQUEST_CAREGIVER", {"message": message}) is not None:
            if contacts and key == "med_deflect":
                return out(r["auto_med_deflect_named"].format(name=contacts[0]["name"]))
            return out(r["auto_" + key])
        if contacts and key == "med_deflect":
            return out(r["med_deflect_named"].format(name=contacts[0]["name"]), wait=True)
        return out(r[key], wait=True)

    def _medicine_action(
        self, uid: int, text: str, intent: str, lang: str, out: Callable[..., TurnResult],
        dose_id: int | None = None,
    ) -> TurnResult:
        r = rp.R[rp.lang_or_default(lang)]
        due = self.core.due_medicines(uid)["current"]
        if not due:
            return out(r["med_none_due"])
        said = set(normalize(text).split(" "))
        named = [d for d in due if said & set(normalize(d["name"]).split(" "))]
        announced = [d for d in due if d["id"] == dose_id]
        if announced:  # "हो" right after the prompt for this dose
            target = announced[0]
        elif len(named) == 1:
            target = named[0]
        elif not named and len(due) == 1:
            target = due[0]  # still verified by a spoken yes/no below
        else:
            names = ", ".join(d["name"] for d in (named or due))
            return out(r["med_which"].format(names=names))
        if intent == "MED_TAKEN":
            if self._act(uid, "MEDICINE_TAKEN", {"dose_id": target["id"]}) is None:
                return out(r["confirm_taken"].format(name=target["name"], dose=target["dose"]), wait=True)
            res = out(r["auto_taken"].format(name=target["name"], dose=target["dose"]))
            res.screen = "saved"
            return res
        try:
            done = self._act(uid, "MEDICINE_SNOOZE", {"dose_id": target["id"]})
        except CoreError as exc:
            if exc.status != 409:
                raise
            msg = {"message": "Aaji kept putting off a medicine reminder."}
            if self._act(uid, "REQUEST_CAREGIVER", msg) is None:
                return out(r["med_no_more_snooze"], wait=True)
            return out(r["auto_no_more_snooze"])
        if done is None:
            return out(r["confirm_snooze"], wait=True)
        return out(r["auto_snooze"])

    def _chat_reply(
        self, uid: int, text: str, lang: str, now: datetime | None = None, llm_reply: str = "",
        opener_followup: str = "",
    ) -> tuple[str, str, bool]:
        """(text for the screen, text for the voice, written by the LLM?). The voice text may carry Timbre voice
        tags the LLM chose. `llm_reply` is the reply from the unified call; only chat/unclear turns pass it."""
        now = now or self.clock()
        reply: str | None = None
        speech = ""
        raw = llm_reply or None
        challenged = False
        view = self.memory.view(uid, now)
        user = self.core.user(uid)
        context = self._user_context(uid, now, user, text)
        context += self._story_recall(uid, text)
        style = user.get("speech_style") or {}
        if style.get("simple"):
            context += (
                "\nSPEECH STYLE: Use short sentences and familiar everyday words. Keep the same meaning and all exact "
                "numbers and times."
            )
        if opener_followup:
            context += (
                "\nFIRST GREETING FOLLOW-UP: Refer naturally to this one most recent unresolved item from yesterday, "
                "and ask how it went. Do not introduce another event: " + opener_followup
            )
        if raw is None and self.evon is not None and self._llm_remaining() >= _MIN_LLM_BUDGET_S:
            raw = self.evon.companion_reply(
                text, lang, now, history=view.messages, interests=user.get("interests") or [],
                timeout=self._llm_remaining(), context=context, memory=view.block,
            )
        while raw is not None:
            # voice tags out first, so the boundary checks see only words
            clean, voiced = split_voice_tags(raw)
            if clean is not None:  # same words on the screen and in the voice (the leading tag stays on the voice)
                clean, voiced = strip_filler(clean, user_text=text), strip_filler_voiced(voiced, user_text=text)
            reply, reasons = sanitize_companion(clean, lang, user_text=text)
            if reply is not None:
                if clean is not None and reply == clean.strip() and voiced != reply:
                    speech = voiced  # untrimmed: the tags still sit on the right words
                break
            log.warning("companion reply rejected (%s)", ",".join(reasons))
            if clean is not None:
                salvaged = salvage_companion(clean, lang, user_text=text)  # drop the one bad sentence, keep the rest
                if salvaged is not None:
                    reply, raw = salvaged, None
                    break
            if challenged or self.evon is None or self._llm_remaining() < _MIN_LLM_BUDGET_S:
                break
            challenged = True  # one corrective retry, then the fixed line
            raw = self.evon.companion_reply(
                text, lang, now, history=view.messages, interests=user.get("interests") or [],
                timeout=self._llm_remaining(), correction=",".join(reasons), context=context, memory=view.block,
            )
        from_llm = reply is not None
        if reply is None:
            reply = self._specific_clarification(uid, text, lang)
        if not reply and len(text.split()) >= 2:
            # No model reply (none configured, busy, timed out) and no topic to ask about: a real sentence still gets
            # a short listening line, never silence (live run 2026-11-09: five chat turns in a row got no answer).
            pool = _VARIED.get(lang, _VARIED["mr"])
            n = self._listen_i.get(uid, 0)
            self._listen_i[uid] = n + 1
            reply = pool[n % len(pool)]
        if from_llm:  # at most one question, not in every reply, never the same one twice in a day
            shaped = shape_questions(reply, self.memory.asked_today(uid, now), self.memory.previous_reply_was_question(uid, now))
            if shaped != reply:
                reply, speech = shaped, ""  # the voice tags sat on the old words: say the shaped reply plainly
        return reply, speech, from_llm

    # ---- live web facts ---------------------------------------------------------------------------------
    def prepare(self, text: str, language_code: str | None = None) -> dict[str, Any]:
        """FAST pre-check for the voice agent (no core-api, no LLM, no search): will this turn probably need a live
        web lookup? Rules only. A safety / medicine / health sentence is never web. A wrong "yes" only costs one
        spoken "बघतो…"; the real decision is still the LLM's in /turn."""
        lang = _detected_reply_language(language_code) or detect_language(text, "mr")
        r = rp.R[rp.lang_or_default(lang)]
        web = (
            bool(_WEB_LIKELY.search(text))
            and not (is_emergency(text) or is_distress(text) or has_failsafe_word(text) or has_health_word(text))
            and not _WEB_BLOCK.search(text)
            and not symptom_category(text)
        )
        return {"needs_web": web, "filler": r["web_filler"] if web else "", "hold": r["web_hold"], "language": lang}

    def _city_for(self, uid: int) -> str:
        """Her city: the family's profile value, else the household ARJUN_CITY. Never guessed."""
        try:
            city = str(self.core.user(uid).get("city") or "").strip()
        except (CoreError, httpx.HTTPError):
            city = ""
        return city or os.environ.get("ARJUN_CITY", "").strip()

    def _news_domains(self, uid: int) -> list[tuple[str, str]]:
        """(domain, family label) for every rss / link the family added: the ONLY news sources Arjun may use."""
        try:
            links = self.core.app_links(uid)
        except (CoreError, httpx.HTTPError):
            return []
        out: list[tuple[str, str]] = []
        for link in links:
            if link.get("kind") in ("rss", "link"):
                host = web_search.host_of(str(link.get("value") or ""))
                if host and host not in [d for d, _ in out]:
                    out.append((host, str(link.get("label") or host)))
        return out

    def _weather_line(self, uid: int, city: str, lang: str) -> str | None:
        return weather.current_weather(city, rp.lang_or_default(lang))

    def _city_followup(self, uid: int, text: str, lang: str, trace: dict[str, Any], t0: float) -> TurnResult | None:
        """The two short answers after "which city?": the city itself, then a yes/no to keeping it."""
        state = self._city_state.get(uid)
        if state is None:
            return None
        kind, city, expires = state
        if self._mono() > expires:
            self._city_state.pop(uid, None)
            return None
        r = rp.R[rp.lang_or_default(lang)]
        norm = normalize(text)
        toks = tokens(norm)

        def out(reply: str, how: str, filler: str = "") -> TurnResult:
            return TurnResult(reply, "CHAT", "companion", lang, filler=filler,
                              trace=self._t({**trace, "intent": "CHAT", "web": how}, t0))

        if kind == "ask":
            self._city_state.pop(uid, None)
            if len(toks) > 4 or _WEB_BLOCK.search(text) or symptom_category(text):
                return None  # not a city: the normal turn handles it
            named = " ".join(text.replace("मध्ये", " ").replace("चं", " ").replace("चे", " ").split()).strip(" .,?!")
            line = self._weather_line(uid, named, lang) if named else None
            if not line:
                return out(r["web_none"], "weather_failed")
            self._city_state[uid] = ("save", named, self._mono() + 120)
            return out(line + r["web_city_offer"], "weather", r["web_filler"])
        self._city_state.pop(uid, None)  # "save": one yes/no, then done
        if has_any(norm, YES) and not has_any(norm, NO):
            try:
                self.core.patch_user(uid, {"city": city})
            except (CoreError, httpx.HTTPError) as exc:
                log.warning("could not save the city (%s)", type(exc).__name__)
                return out(r["web_none"], "city_not_saved")
            return out(r["web_city_saved"], "city_saved")
        if has_any(norm, NO):
            return out(r["web_city_declined"], "city_declined")
        return None

    def _web_turn(self, uid: int, text: str, query: str, lang: str, trace: dict[str, Any], t0: float) -> TurnResult | None:
        """A live-facts question. Weather: Open-Meteo (her city, else ARJUN_CITY, else ask once). News: Tavily results
        from the family's approved domains ONLY, source named aloud. Anything else: any search result. The LLM answers
        from the snippets only. Never for medicine / health words. Any failure is the fixed "no information" line."""
        r = rp.R[rp.lang_or_default(lang)]

        def done(reply: str, how: str, source: str = "rules") -> TurnResult:
            return TurnResult(
                reply, "CHAT", "companion", lang, source=source, filler=r["web_filler"],
                trace=self._t({**trace, "intent": "CHAT", "web": how}, t0),
            )

        if _WEB_BLOCK.search(text) or symptom_category(text):
            return TurnResult(
                r["web_health"], "CHAT", "companion", lang, trace=self._t({**trace, "intent": "CHAT", "web": "blocked"}, t0)
            )
        # one wall-clock budget for the whole lookup, kept under the voice path's 9 s wait
        end = self._llm_deadline - self._llm_timeout_s + _WEB_TURN_BUDGET_S
        try:
            if _WEATHER.search(text):
                city = self._city_for(uid)
                if not city:  # ask once; her answer is handled by _city_followup
                    self._city_state[uid] = ("ask", "", self._mono() + 120)
                    return TurnResult(r["web_city"], "CHAT", "companion", lang, trace=self._t({**trace, "intent": "CHAT", "web": "ask_city"}, t0))
                line = self._weather_line(uid, city, lang)
                return done(line, "weather") if line else done(r["web_none"], "weather_failed")
            news = bool(_NEWS.search(text) or _NEWS.search(query))
            allowed = self._news_domains(uid)[:5] if news else []
            if news and not allowed:
                return done(r["web_none"], "news_no_source")
            search_s = min(web_search.TIMEOUT_S, end - self._mono() - _WEB_ANSWER_RESERVE_S)
            if search_s < 1.0:
                return done(r["web_none"], "no_budget")
            results = web_search.search(
                query or text, lang, timeout_s=search_s, domains=[d for d, _ in allowed] or None
            )
            source = ""
            if news and results:
                # name the source and answer from THAT result alone, so the spoken name is the true origin
                for d, label in allowed:
                    hit = [x for x in results if web_search.host_allowed(x.get("source_domain", ""), [d])]
                    if hit:
                        results, source = hit[:1], label
                        break
                else:
                    results = None
            if not results:
                return done(r["web_none"], "search_failed" if not news else "news_no_approved_result")
            self._llm_deadline = end  # the answer call may use what is left of the lookup budget
            if self.evon is None or not hasattr(self.evon, "web_answer") or self._llm_remaining() < _MIN_LLM_BUDGET_S:
                return done(r["web_none"], "no_llm")
            raw = self.evon.web_answer(text, lang, results, timeout=self._llm_remaining())  # type: ignore[attr-defined]
            clean, _ = split_voice_tags(raw) if raw else (None, "")
            reply, _ = sanitize_companion(clean, lang, user_text=text) if clean else (None, [])
            if not reply:
                return done(r["web_none"], "answer_failed")
            if source:
                reply = r["web_source"].format(src=source, answer=reply)
            return done(reply, "search_news" if news else "search", "llm")
        except Exception as exc:  # noqa: BLE001 - a web lookup never breaks a turn
            log.info("web turn failed: %s", type(exc).__name__)
            return done(r["web_none"], "error")

    def _specific_clarification(self, uid: int, text: str, lang: str) -> str:
        """Topic-naming repair for an uncertain transcript; never emit a generic repeat prompt."""
        norm = normalize(text)
        topic = ""
        question = ""
        try:
            for contact in self.core.contacts(uid):
                name = str(contact.get("name") or "").strip()
                if name and normalize(name) in norm:
                    topic, question = name.casefold(), f"तुम्ही {name}बद्दल म्हणताय का?"
                    break
        except (CoreError, httpx.HTTPError):
            pass
        if not topic:
            choices = (
                (("औषध", "गोळी", "दवा", "medicine"), "औषध", "औषधाबद्दल विचारताय का?"),
                (("जेवण", "भूक", "भाजी", "खाल्ली", "खाल्ले", "खायला", "food"), "जेवण", "तुम्ही जेवणाबद्दल सांगताय का?"),
                (("कॉल", "फोन", "call", "फोनवर"), "फोन", "तुम्हाला फोनबद्दल मदत हवी आहे का?"),
                (("भजन", "गाणं", "गाणी", "यूट्यूब", "youtube", "video", "व्हिडिओ"), "मीडिया", "तुम्हाला गाणं किंवा व्हिडिओ लावायचा आहे का?"),
                (("पुणे", "मुंबई", "गाव", "श्रीलंका", "ठिकाण", "कुठे"), "ठिकाण", "तुम्ही त्या ठिकाणाबद्दल विचारताय का?"),
                (("बाग", "झाड", "फुल", "garden"), "बाग", "तुम्ही बागेबद्दल सांगताय का?"),
                (("डॉक्टर", "doctor", "भेट"), "डॉक्टर", "तुम्ही डॉक्टरांच्या भेटीबद्दल विचारताय का?"),
                (("कलेक्शन", "collection", "फोटो"), "कलेक्शन", "तुम्ही फोटोच्या कलेक्शनबद्दल बोलताय का?"),
                (("एप्रिल", "कॅलेंडर", "calendar", "रिकामं"), "कॅलेंडर", "तुम्ही कॅलेंडरमधल्या तारखांबद्दल बोलताय का?"),
            )
            words = set(tokens(norm))
            for needles, key, prompt in choices:
                # whole words or their case forms ("फोनवर"), never a piece of a longer word: "कॉलेजला" is not "कॉल"
                if any(w == n or (w.startswith(n) and len(w) - len(n) <= 3 and not n.isascii()) or (n.isascii() and w == n)
                       for n in needles for w in words):
                    topic, question = key, prompt
                    break
        if not topic:
            return ""
        previous = self._last_clarification.get(uid)
        now = self._mono()
        if previous and previous[0] == topic and now - previous[1] < 600:
            log.info("clarification suppressed: same topic repeated")
            return ""
        self._last_clarification[uid] = (topic, now)
        if lang == "hi":
            question = {
                "औषध": "आप दवा के बारे में पूछ रहे हैं?", "जेवण": "आप खाने के बारे में बता रहे हैं?",
                "फोन": "क्या आपको फोन करने में मदद चाहिए?", "मीडिया": "क्या आप गाना या वीडियो चलाना चाहते हैं?",
                "ठिकाण": "क्या आप उस जगह के बारे में पूछ रहे हैं?",
                "बाग": "क्या आप बगीचे के बारे में बता रहे हैं?",
                "डॉक्टर": "क्या आप डॉक्टर की मुलाकात के बारे में पूछ रहे हैं?",
                "कलेक्शन": "क्या आप फोटो कलेक्शन के बारे में बता रहे हैं?",
                "कॅलेंडर": "क्या आप कैलेंडर की तारीखों के बारे में पूछ रहे हैं?",
            }.get(topic, f"क्या आप {topic} के बारे में पूछ रहे हैं?")
        elif lang == "en":
            question = {
                "औषध": "Are you asking about a medicine?", "जेवण": "Are you talking about food?",
                "फोन": "Would you like help with a phone call?", "मीडिया": "Would you like a song or video?",
                "ठिकाण": "Are you asking about that place?",
                "बाग": "Are you talking about the garden?",
                "डॉक्टर": "Are you asking about a doctor appointment?",
                "कलेक्शन": "Are you talking about the photo collection?",
                "कॅलेंडर": "Are you asking about the dates in your calendar?",
            }.get(topic, f"Are you asking about {topic}?")
        return question

    def _symptom(
        self, uid: int, text: str, category: str, lang: str, trace: dict[str, Any], t0: float, now: datetime
    ) -> TurnResult:
        """A health complaint that is not an emergency (boundary 5): no advice, no diagnosis, no question. The family
        sees a "watch" note only with the alert consent; the reply says so ONLY if a note really exists (boundary 14)."""
        r = rp.R[rp.lang_or_default(lang)]
        try:
            told = self.core.health_complaint(uid, category)
        except (CoreError, httpx.HTTPError) as exc:
            log.warning("symptom: could not tell the family: %s", exc)
            told = False
        res = TurnResult(
            r["symptom_noted" if told else "symptom_not_noted"], "SYMPTOM", "companion", lang,
            trace=self._t({**trace, "symptom": category}, t0), screen="story",
        )
        self._convo_at[uid] = self._mono()  # the conversation goes on
        return res

    def _lonely(
        self, uid: int, text: str, lang: str, trace: dict[str, Any], t0: float, now: datetime
    ) -> TurnResult:
        """A warm fixed reply that points to the people in her life (never "I missed you", never a feeling
        claimed by Arjun), then keep listening. The family hears of it only with consent (core-api decides)."""
        r = rp.R[rp.lang_or_default(lang)]
        try:
            names = [c["name"] for c in self.core.contacts(uid)]
        except (CoreError, httpx.HTTPError) as exc:
            log.warning("lonely: contacts unavailable: %s", exc)
            names = []
        try:
            self.core.lonely(uid)
        except (CoreError, httpx.HTTPError) as exc:
            log.warning("lonely: could not tell the family: %s", exc)
        reply = r["lonely"].format(names=", ".join(names[:3])) if names else r["lonely_no_contacts"]
        res = TurnResult(reply, "LONELY", "companion", lang, trace=self._t(trace, t0), screen="story")
        self._convo_at[uid] = self._mono()
        return res

    def _distress(self, uid: int, lang: str, trace: dict[str, Any], t0: float) -> TurnResult:
        return self._safety(uid, lang, trace, t0, kind="distress")

    def _safety(
        self, uid: int, lang: str, trace: dict[str, Any], t0: float, kind: str
    ) -> TurnResult:
        """Shared path for distress and physical emergency: stop everything, clear pending actions,
        record the event (core-api alerts family only per consent - emergency policy is PENDING a
        decision by the team), and speak the fixed template."""
        self._last_safety[uid] = self._mono()  # no reminder is spoken over / right after this
        self._drafts.pop(uid, None)
        self._convo_at.pop(uid, None)  # small talk pauses; the session memory stays (with a safety note, _record_turn)
        # Every core call is best-effort: the spoken safety reply below is returned regardless.
        try:
            pending = self.core.pending(uid)
            if pending is not None:  # a stray "yes" must not execute anything after distress
                self.core.reject(uid, pending["id"])
        except (CoreError, httpx.HTTPError) as exc:
            log.error("%s: could not clear pending action: %s", kind, exc)
        alerted = False
        try:
            # emergency: core-api ALWAYS alerts the family (dashboard); distress: only with consent.
            # The reply below may claim the family was told ONLY when this says it was.
            alerted = bool((self.core.distress(uid, kind) or {}).get("caregiver_alerted"))
        except (CoreError, httpx.HTTPError) as exc:
            log.error("%s: could not record event / alert caregiver: %s", kind, exc)
        local = replies_langs.safety_reply(lang, kind, alerted)  # bn gu kn ml pa ta te: fixed line in her own language
        if local is not None:
            return TurnResult(local, "EMERGENCY" if kind == "emergency" else "DISTRESS", "safety", lang,
                              trace=self._t(trace, t0), screen="safety")
        lang = lang if lang in {"mr", "hi", "en"} else "en"
        family_obj = self._family_obj(uid, lang)
        ask_call = {
            "mr": "मुलाला फोन करायचा असेल तर 'मुलाला फोन लाव' म्हणा.",
            "hi": "परिवार को फोन करना हो तो 'परिवार को फोन लगाओ' कहें।",
            "en": "If you need family, say 'call my family'.",
        }[lang]
        if kind == "emergency":
            if lang == "mr":
                reply = (f"मी {family_obj} लगेच कळवलं आहे. जमलं तर 112 ला फोन करा, नाहीतर जवळच्या कोणाला हाक मारा." if alerted
                         else f"जमलं तर 112 ला फोन करा, नाहीतर जवळच्या कोणाला हाक मारा. {ask_call}")
            elif lang == "hi":
                reply = (f"मैंने {family_obj} तुरंत बता दिया है। हो सके तो 112 पर कॉल करें, या पास किसी को आवाज़ दें।" if alerted
                         else f"हो सके तो 112 पर कॉल करें, या पास किसी को आवाज़ दें। {ask_call}")
            else:
                reply = (f"I alerted {family_obj}. If you can, call 112 or call out to someone near you." if alerted
                         else f"If you can, call 112 or call out to someone near you. {ask_call}")
        elif alerted and lang == "mr":
            reply = f"कुठे त्रास होतोय, सांगा. मी {family_obj} कळवलं आहे."
        elif alerted and lang == "hi":
            reply = f"कहाँ परेशानी हो रही है, बताइए। मैंने {family_obj} बता दिया है।"
        elif alerted:
            reply = f"Tell me what is troubling you. I alerted {family_obj}."
        else:
            reply = f"कुठे त्रास होतोय, सांगा. {ask_call}" if lang == "mr" else (
                f"कहाँ परेशानी हो रही है, बताइए। {ask_call}" if lang == "hi" else f"Tell me what is troubling you. {ask_call}"
            )
        intent = "EMERGENCY" if kind == "emergency" else "DISTRESS"
        return TurnResult(reply, intent, "safety", lang, trace=self._t(trace, t0), screen="safety")

    def _family_obj(self, uid: int, lang: str = "mr") -> str:
        """The person a safety / help line names: the son, else another family member (never a doctor),
        else "your family". A lookup failure never becomes an arbitrary first contact."""
        try:
            contacts = self.core.contacts(uid) or []
        except (CoreError, httpx.HTTPError) as exc:
            log.warning("family lookup failed: %s", exc)
            contacts = []
        chosen = next((c for c in contacts if _is_son(str(c.get("relation", "")))), None)
        if chosen is None:
            chosen = next((c for c in contacts if not _is_doctor(str(c.get("relation", "")))), None)
        name = str(chosen.get("name", "")).strip() if chosen is not None else ""
        if not name:
            return _FAMILY_FALLBACK.get(lang, _FAMILY_FALLBACK["mr"])
        if lang == "hi":
            return f"{name} को"
        if lang == "en":
            return name
        return f"{name}ला"

    @staticmethod
    def _t(trace: dict[str, Any], t0: float) -> dict[str, Any]:
        trace["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return trace
