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
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable
from urllib.parse import quote

import httpx

from . import config
from . import replies as rp
from .app_replies import A
from .appcmd import (
    APP_INTENTS,
    CONTROLS,
    MEDIA_CONTROL,
    NEWS_READ,
    OPEN_LINK,
    OPEN_MEDIA,
    OPEN_WHATSAPP,
    clean_query,
    covers,
    is_media_request,
    media_kind,
    media_topic,
    name_matches,
)
from .checkins import answer_from_text
from .clock import local_now
from .core_client import CoreClient, CoreError
from .distress import is_distress, is_emergency, is_lonely, symptom_category
from .media_understanding import understand_media
from .evon import (
    EvonClient,
    sanitize_companion,
    split_voice_tags,
    strip_filler,
    strip_filler_voiced,
)
from .parser import (
    MED_TAKEN_WORDS,
    NO,
    SNOOZE_WORDS,
    STOP,
    Draft,
    Parsed,
    Profile,
    apply_text,
    has_med_word,
    parse,
)
from .readings import format_bp, parse_bp
from .textutil import collapse_repeats, detect_language, has_any, normalize, tokens

log = logging.getLogger("reasoning.turn")

_MIN_LLM_BUDGET_S = 0.3  # less than this left in the turn's LLM budget: do not start a call
# What the LLM may SUGGEST for a turn the rules could not read. Medicines, confirmations, forgetting and
# sharing are deliberately absent: those come only from the deterministic parser.
_LLM_INTENTS = frozenset(
    {"CREATE_REMINDER", "LIST_TODAY", "GET_APPOINTMENT", "CALL_FAMILY_REMINDER", "REQUEST_CAREGIVER", "CHAT",
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
_FAMILY_FALLBACK = {"mr": "तुमच्या घरच्यांना", "hi": "आपके घरवालों को", "en": "your family"}


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
_HISTORY_IDLE = timedelta(minutes=30)  # a longer silence starts a fresh conversation
_CONVO_WINDOW_S = 300.0  # a companion chat is "active" this long after its last companion turn
_SHORT_TURN_WORDS = 4  # a bare "झालं" / "झाला ना" is this short; a story sentence is longer
_HISTORY_CARE_CHARS = 140  # a care turn goes into the LLM history as short text only
# Bare answers that are not "stop talking": in a chat they are part of the chat. "नको" / "nako" stays a stop.
_SOFT_ANSWERS = frozenset({"CONFIRM_YES", "CONFIRM_NO"})
_STOP_NO = ("nako", "नको", "mat", "नही")

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


class TurnEngine:
    def __init__(
        self,
        core: CoreClient,
        evon: EvonClient | None = None,
        clock: Callable[[], datetime] = local_now,
        llm_timeout_s: float = config.LLM_TIMEOUT_S,
        history_exchanges: int = config.LLM_HISTORY_EXCHANGES,
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
        self._history_cap = history_exchanges * 2
        self._mono = mono
        self._llm_deadline = 0.0
        self._last_safety: dict[int, float] = {}  # user -> monotonic time of the last safety reply (T8)
        self._drafts: dict[int, Draft] = {}  # in-memory slot-filling state (single instance)
        self._media_ask: dict[int, float] = {}  # user -> mono time of "काय लावू?" waiting for the answer
        self._media_choice: dict[int, _MediaChoice] = {}  # user -> the three cards waiting for an answer
        self._chat_counter: dict[int, int] = {}
        self._convo_at: dict[int, float] = {}  # user -> monotonic time of the last companion turn
        # This conversation only: in memory, capped, dropped after idle or distress. Never stored.
        self._history: dict[int, list[tuple[datetime, str, str]]] = {}

    # ------------------------------------------------------------------ public
    def _llm_remaining(self) -> float:
        """Seconds left of this turn's ONE LLM time budget (the voice path waits about 5 s in total)."""
        return max(0.0, self._llm_deadline - self._mono())

    def handle(self, user_id: int, text: str) -> TurnResult:
        t0 = time.perf_counter()
        self._llm_deadline = self._mono() + self._llm_timeout_s
        text = collapse_repeats(text)  # recognizer artifacts ("हो हो हो कर कर कर ...") before ANY parsing or safety check
        trace: dict[str, Any] = {}
        # 0/1. emergency, then distress: both override everything and must not depend on
        # core-api being reachable. The replies are fixed templates, so a failed lookup only
        # costs the language default.
        if is_emergency(text) or is_distress(text) or "त्रास" in text and ("होतोय" in text or "होते" in text or "होता" in text):
            self._media_choice.pop(user_id, None)  # an emergency closes the cards: nothing is playing
            try:
                default_lang = self.core.user(user_id)["language"]
            except (CoreError, httpx.HTTPError, KeyError):
                default_lang = "mr"
            lang = detect_language(text, default_lang)
            if is_emergency(text):
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
        lang = detect_language(text, user["language"])
        r = rp.R[rp.lang_or_default(lang)]
        now = self.clock()

        # 2. AI disclosure
        if has_any(normalize(text), _AI_QUESTIONS):
            return TurnResult(r["ai_disclosure"], "UNKNOWN", "care", lang, trace=self._t(trace, t0))

        # 3. intent
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
            picked = self._answer_choice(user_id, text, lang, trace, t0)
            if picked is not None:
                if picked.intent == "CHAT" and picked.mode == "companion":
                    self._convo_at[user_id] = self._mono()
                if picked.mode != "safety":
                    self._remember(user_id, now, text, picked)
                log.info(json.dumps({"user": user_id, "intent": picked.intent, **picked.trace}))
                return picked
        # A meal / walk prompt that a session really spoke takes a clear done/skipped answer - but only when
        # nothing else is waiting: no yes/no, no reminder draft, no undo window, no recent medicine prompt.
        if pending is None and draft is None and recent is None and self._recent_dose(user_id) is None:
            reading = self._record_bp(user_id, text, lang, trace, t0)
            if reading is not None:
                return reading
            checkin = self._answer_open_checkin(user_id, text, lang, trace, t0)
            if checkin is not None:
                return checkin
        answerable = pending["action_type"] if pending else (recent["action_type"] if recent else None)
        if answerable is None and self._recent_dose(user_id) is not None:
            answerable = "MEDICINE_TAKEN"  # "हो" / "घेतली" right after a medicine prompt
        conversing = pending is None and draft is None and self._conversing(user_id)
        parsed, source = self._intent(
            text, profile, now, lang, answerable is not None, draft, answerable, conversing=conversing
        )
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

        # 4. dispatch
        try:
            result = self._dispatch(user_id, text, parsed, pending, draft, profile, now, lang)
        except CoreError as exc:
            log.warning("core error: %s", exc)
            # a half-built reminder must not swallow her next sentences (seen in the 2026-10-31 smoke run)
            self._drafts.pop(user_id, None)
            result = TurnResult(r["error"], parsed.intent, "care", lang)
        if result.source != "llm":  # a companion reply the LLM wrote already says so
            result.source = source
        result.trace = self._t({**trace, "intent": parsed.intent}, t0)
        if result.intent == "CHAT" and result.mode == "companion":
            self._convo_at[user_id] = self._mono()
        if result.mode != "safety":
            self._remember(user_id, now, text, result)
        log.info(json.dumps({"user": user_id, "intent": parsed.intent, **result.trace}))
        return result

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
        return Parsed("OPEN_MEDIA", 0.85, p.language, topic="youtube", query=query)

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
            self._media_ask[uid] = self._mono()  # the existing 2-minute "what should I play?" state
            return res(a["ask_media_kind"])
        if kind == "news":
            return self._offer_news(uid, text, links, a, res)

        # A family favourite she NAMED (and that covers everything she asked for) is the best match. A category
        # alone ("भजन लाव") goes to search + three cards, so the family's curation never hides other choices.
        named = self._named_links(links, text, "", _YT_MUSIC)
        named = [x for x in named if not query or covers(self._link_names(x), query)]
        if specific and named:
            pick = named[0]
            if pick["kind"] == "youtube_query":
                query = pick["value"]  # a saved search ("जुनी मराठी भजनं")
            else:
                return res(a["play"], self._media_action(self._open_link(pick), query))

        if not query:  # a category with no words: search the category in Marathi
            query = {
                "music": "मराठी गाणी", "devotional": "मराठी भजन", "recipe": "मराठी रेसिपी",
                "exercise": "मराठी व्यायाम", "video": "मराठी व्हिडिओ",
            }.get(kind, "")
        query = self._with_marathi(query)
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
    def _with_marathi(query: str) -> str:
        """Search in Marathi unless she already said it: "पुरणपोळी" -> "पुरणपोळी मराठी"."""
        q = " ".join(query.split())[:100]
        return q if not q or "मराठी" in q else f"{q} मराठी"

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

    def _remember(self, uid: int, now: datetime, text: str, res: TurnResult) -> None:
        """The LLM's memory of THIS conversation: companion turns in full, care turns as short text. In memory
        only, never stored. Medicine turns are left out (their wording comes only from SQL templates)."""
        if res.intent in (
            "MED_TAKEN", "MED_SNOOZE", "MEDICAL_QUESTION", "PENDING_REPEAT", "EMERGENCY", "DISTRESS",
            "BP_READING",
        ):
            return
        if res.intent == "CHAT" and res.mode == "companion":
            return  # _chat_reply already stored the exchange
        turns = self._recent_history(uid, now)
        turns += [
            (now, "user", text.strip()[:_HISTORY_CARE_CHARS]),
            (now, "assistant", res.reply.strip()[:_HISTORY_CARE_CHARS]),
        ]
        self._history[uid] = turns[-self._history_cap:]

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
    def _record_bp(self, uid: int, text: str, lang: str, trace: dict[str, Any], t0: float) -> TurnResult | None:
        """Store a spoken BP reading and repeat the same numbers back. Never a judgement, never advice."""
        numbers = parse_bp(text)
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

    def _checkin_line(self, uid: int, kind: str, lang: str, attempt: int = 1) -> str:
        """A fixed check-in prompt. A snack on a class day also names that class, from SQL only."""
        r = rp.R[rp.lang_or_default(lang)]
        prompt = r.get(f"checkin_prompt_{kind}") or r["checkin_prompt_breakfast"]
        if kind == "snack":
            event = self._evening_appointment(uid)
            if event is not None:
                prompt = (
                    f"{prompt} "
                    + r["checkin_class_today"].format(
                        when=rp.say_time(event["at"][11:16], lang), title=event["label"]
                    )
                )
        if attempt > 1:
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

    def _answer_open_checkin(
        self, uid: int, text: str, lang: str, trace: dict[str, Any], t0: float
    ) -> TurnResult | None:
        """Record a spoken done / skipped answer for the open check-in, on a fixed template."""
        try:
            c = self.core.open_checkin(uid)
        except (CoreError, httpx.HTTPError) as exc:
            log.warning("could not read the open check-in: %s", exc)
            return None
        if not c or not c.get("heard"):
            return None  # queued but never spoken: the words are not an answer to it
        answer = answer_from_text(text)
        if answer is None:
            return None
        try:
            self.core.answer_checkin(uid, c["id"], answer)
        except CoreError as exc:
            log.warning("could not record the check-in answer: %s", exc)
            return None
        r = rp.R[rp.lang_or_default(lang)]
        key = f"checkin_{answer}_{c['kind']}"
        intent = "CHECKIN_DONE" if answer == "done" else "CHECKIN_SKIPPED"
        return TurnResult(
            r.get(key, r["checkin_done_breakfast"]), intent, "care", lang, trace=self._t(trace, t0)
        )

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

    def deliver_next(self, uid: int, session: str) -> dict[str, Any] | None:
        """Claim the next waiting reminder / medicine prompt and render its fixed wording, or return None.

        Never while a yes/no is pending or just after a safety reply. The claim is atomic in core-api, so two open
        sessions can never get the same item. Nothing is marked spoken here: the voice session does that after
        playback finished. No LLM is involved.
        """
        b = self.busy(uid)
        if b["pending"] or b["safety_hold"]:
            return None
        d = self.core.delivery_next(uid)
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
                text = self._checkin_line(uid, d["label"], lang, d["attempt"])
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
        return {
            "delivery_id": d["id"], "kind": d["kind"], "text": text, "screen": screen, "item": item,
            "awaiting_confirmation": ask, "language": lang,
        }

    def deliver_spoken(self, uid: int, delivery_id: int, session: str) -> None:
        self.core.delivery_spoken(uid, delivery_id, session)

    def deliver_release(self, uid: int, delivery_id: int, session: str, reason: str) -> None:
        self.core.delivery_release(uid, delivery_id, session, reason)

    def opener(self, user_id: int) -> str | None:
        """Proactive 'Shikva na' opener - scheduler-triggered, gated by caregiver-set hours."""
        user = self.core.user(user_id)
        if not self.core.opener_allowed(user_id) or not user["interests"]:
            return None
        lang = rp.lang_or_default(user["language"])
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
    ) -> tuple[Parsed, str]:
        rules = parse(text, profile, now, lang, has_pending, pending_action)
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
        # Media understanding. The rules know this is a media-ish request (YouTube / बघायचं / लाव / a recipe
        # question) but not always WHAT it is. One strict-JSON call decides kind / topic / specific, with a 3 s
        # budget; a slow or invalid answer leaves the rule answer in place. Safety, medicine and reminders were
        # already decided above and never reach this call.
        if (
            self.evon is not None
            and not has_pending
            and rules.intent in ("UNKNOWN", "CHAT", OPEN_MEDIA)
            and is_media_request(text)
            and self._llm_remaining() >= _MIN_LLM_BUDGET_S
        ):
            understood = understand_media(self.evon, text, timeout=min(3.0, self._llm_remaining()))
            return (
                Parsed(
                    OPEN_MEDIA, 0.85, lang, rules.draft, topic="media", query=understood.topic,
                    media_kind=understood.kind, media_specific=understood.specific,
                ),
                understood.source,
            )
        if rules.intent == "UNKNOWN" and symptom_category(text):
            return rules, "rules"  # a health complaint gets the fixed template; the LLM never hears it
        if conversing and rules.intent == "UNKNOWN":
            return rules, "rules"  # mid-chat an odd turn is chat (_reshape); the intent extractor is not asked
        # The LLM is asked ONLY about turns the rules cannot read. Care commands, times, medicines,
        # confirmations and safety were decided above/before and never wait for it. Nor does it hear
        # anything while a yes/no is pending: the only valid turns then are an answer or a correction.
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
        # confirmations / decline always come from the deterministic parser (safer, no latency)
        if rules.intent in (
            "CONFIRM_YES", "CONFIRM_NO", "DECLINE_TOPIC", "FORGET_MEMORY", "MED_TAKEN", "MED_SNOOZE",
            "TIME_QUERY", "NEXT_UP", "GREETING", "HEARING_CHECK",
        ):
            return rules, "rules"
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

        if intent == "CHAT":
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
            reply, speech, from_llm = self._chat_reply(uid, text, lang, now)
            res = out(reply, "companion")
            res.speech = speech
            if from_llm:
                res.source = "llm"
            return res

        return out(r["unknown"])

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
        message = (
            "Aaji asked to set a medicine time. Please add it on the dashboard."
            if key == "med_family_sets"
            else "Aaji has a question about medicine. Please call her; Arjun did not answer it."
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
        self, uid: int, text: str, lang: str, now: datetime | None = None
    ) -> tuple[str, str, bool]:
        """(text for the screen, text for the voice, written by the LLM?). The voice text may carry Timbre voice
        tags the LLM chose."""
        now = now or self.clock()
        reply: str | None = None
        speech = ""
        if self.evon is not None and self._llm_remaining() >= _MIN_LLM_BUDGET_S:
            recent = self._recent_history(uid, now)
            interests = self.core.user(uid).get("interests") or []
            raw = self.evon.companion_reply(
                text, lang, now, history=[(role, said) for _, role, said in recent], interests=interests,
                timeout=self._llm_remaining(),
            )
            # voice tags out first, so the boundary checks see only words
            clean, voiced = split_voice_tags(raw) if raw else (None, "")
            if clean is not None:  # same words on the screen and in the voice (the leading tag stays on the voice)
                clean, voiced = strip_filler(clean), strip_filler_voiced(voiced)
            # two sentences at most, and no boundary broken (human / missed you / medical / recipes, facts)
            reply, reasons = sanitize_companion(clean, lang)
            if raw and reasons:
                log.warning("companion reply rejected (%s); using the fixed line", ",".join(reasons))
            if reply is not None and clean is not None and reply == clean.strip() and voiced != reply:
                speech = voiced  # untrimmed: the tags still sit on the right words
        from_llm = reply is not None
        if reply is None:
            n = self._chat_counter.get(uid, 0)
            self._chat_counter[uid] = n + 1
            options = rp.CHAT[rp.lang_or_default(lang)]
            reply = options[n % len(options)]
        turns = self._recent_history(uid, now)
        turns += [(now, "user", text), (now, "assistant", reply)]
        self._history[uid] = turns[-self._history_cap:]
        return reply, speech, from_llm

    def _recent_history(self, uid: int, now: datetime) -> list[tuple[datetime, str, str]]:
        turns = self._history.get(uid, [])
        if turns and now - turns[-1][0] > _HISTORY_IDLE:
            turns = []
        return list(turns)

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
        self._remember(uid, now, text, res)
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
        text = r["lonely"].format(names=", ".join(names[:3])) if names else r["lonely_no_contacts"]
        res = TurnResult(text, "LONELY", "companion", lang, trace=self._t(trace, t0), screen="story")
        self._convo_at[uid] = self._mono()
        self._remember(uid, now, text, res)
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
        self._history.pop(uid, None)  # the story stops; nothing resumes after a crisis
        self._convo_at.pop(uid, None)
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
        family_obj = self._family_obj(uid, "mr")
        ask_call = "मुलाला फोन करायचा असेल तर 'मुलाला फोन लाव' म्हणा."
        if kind == "emergency":
            reply = (
                f"मी {family_obj} लगेच कळवलं आहे. 112 वर फोन करा."
                if alerted
                else f"112 वर फोन करा. {ask_call}"
            )
        elif alerted:
            reply = f"कुठे त्रास होतोय, सांगा. मी {family_obj} कळवलं आहे."
        else:
            reply = f"कुठे त्रास होतोय, सांगा. {ask_call}"
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
