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

import httpx

from . import config
from . import replies as rp
from .clock import local_now
from .core_client import CoreClient, CoreError
from .distress import is_distress, is_emergency
from .evon import EvonClient, sanitize_companion
from .parser import MED_TAKEN_WORDS, Draft, Parsed, Profile, apply_text, has_med_word, parse
from .textutil import detect_language, has_any, normalize

log = logging.getLogger("reasoning.turn")

_MIN_LLM_BUDGET_S = 0.3  # less than this left in the turn's LLM budget: do not start a call
# What the LLM may SUGGEST for a turn the rules could not read. Medicines, confirmations, forgetting and
# sharing are deliberately absent: those come only from the deterministic parser.
_LLM_INTENTS = frozenset(
    {"CREATE_REMINDER", "LIST_TODAY", "GET_APPOINTMENT", "CALL_FAMILY_REMINDER", "REQUEST_CAREGIVER", "CHAT",
     "DISTRESS"}
)
_HISTORY_IDLE = timedelta(minutes=30)  # a longer silence starts a fresh conversation

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


class TurnEngine:
    def __init__(
        self,
        core: CoreClient,
        evon: EvonClient | None = None,
        clock: Callable[[], datetime] = local_now,
        llm_timeout_s: float = config.LLM_TIMEOUT_S,
        history_exchanges: int = config.LLM_HISTORY_EXCHANGES,
        mono: Callable[[], float] = time.monotonic,
    ) -> None:
        self.core = core
        self.evon = evon  # the hosted LLM (name kept from the Evon days); None = rules only
        self.clock = clock
        self._llm_timeout_s = llm_timeout_s
        self._history_cap = history_exchanges * 2
        self._mono = mono
        self._llm_deadline = 0.0
        self._drafts: dict[int, Draft] = {}  # in-memory slot-filling state (single instance)
        self._chat_counter: dict[int, int] = {}
        # This conversation only: in memory, capped, dropped after idle or distress. Never stored.
        self._history: dict[int, list[tuple[datetime, str, str]]] = {}

    # ------------------------------------------------------------------ public
    def _llm_remaining(self) -> float:
        """Seconds left of this turn's ONE LLM time budget (the voice path waits about 5 s in total)."""
        return max(0.0, self._llm_deadline - self._mono())

    def handle(self, user_id: int, text: str) -> TurnResult:
        t0 = time.perf_counter()
        self._llm_deadline = self._mono() + self._llm_timeout_s
        trace: dict[str, Any] = {}
        # 0/1. emergency, then distress: both override everything and must not depend on
        # core-api being reachable. The replies are fixed templates, so a failed lookup only
        # costs the language default.
        if is_emergency(text) or is_distress(text):
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
        parsed, source = self._intent(
            text, profile, now, lang, pending is not None, draft, pending["action_type"] if pending else None
        )
        trace["intent_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        if parsed.intent == "DISTRESS":
            return self._distress(user_id, lang, trace, t0)

        # 4. dispatch
        try:
            result = self._dispatch(user_id, text, parsed, pending, draft, profile, now, lang)
        except CoreError as exc:
            log.warning("core error: %s", exc)
            result = TurnResult(r["error"], parsed.intent, "care", lang)
        result.source = source
        result.trace = self._t({**trace, "intent": parsed.intent}, t0)
        log.info(json.dumps({"user": user_id, "intent": parsed.intent, **result.trace}))
        return result

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
    ) -> tuple[Parsed, str]:
        rules = parse(text, profile, now, lang, has_pending, pending_action)
        # A medicine question is always deflected, whatever the LLM thinks it is.
        if rules.intent == "MEDICAL_QUESTION":
            return rules, "rules"
        # In slot-filling, short answers ("udya", "sakali") complete the open reminder draft.
        if draft is not None and rules.intent in ("UNKNOWN", "CHAT", "CREATE_REMINDER"):
            rules.intent = "CREATE_REMINDER"
            return rules, "rules"
        # The LLM is asked ONLY about turns the rules cannot read. Care commands, times, medicines,
        # confirmations and safety were decided above/before and never wait for it.
        if self.evon is None or rules.intent != "UNKNOWN" or self._llm_remaining() < _MIN_LLM_BUDGET_S:
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
            if pending is not None:
                self.core.reject(uid, pending["id"])
            self._drafts.pop(uid, None)
            return out(r["cancelled_retry"] if p.topic == "correction" else r["cancelled"])

        if intent == "DECLINE_TOPIC":
            self._drafts.pop(uid, None)
            if pending is not None:
                self.core.reject(uid, pending["id"])
            self.core.decline(uid)  # ends proactive openers for the day; no re-ask
            return out(r["decline"], "companion")

        # Any non-reminder intent abandons an open reminder draft and stale confirmation.
        if intent != "CREATE_REMINDER":
            self._drafts.pop(uid, None)

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
            self.core.propose(uid, "REQUEST_CAREGIVER", {"message": "Please call me."})
            return out(r["confirm_caregiver"], wait=True)

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
            self.core.propose(uid, "SHARE_STORY", {"story_id": story["id"]})
            return out(r["confirm_share"], "companion", wait=True)

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
            if len(text.split()) >= config.LONG_STORY_WORDS:
                self.core.propose(uid, "SAVE_STORY", {"summary": text.strip()[:2000]})
                return out(r["ask_save_story"], "companion", wait=True)
            return out(self._chat_reply(uid, text, lang, now), "companion")

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
        try:
            self.core.propose(
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
        return out(r["confirm_reminder"].format(task=d.task, when=when), wait=True)

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
        self.core.propose(uid, "COMPLETE_REMINDER", {"reminder_id": target["id"]})
        return out(r["confirm_complete"].format(task=target["task"]), wait=True)

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
        self.core.propose(uid, "REQUEST_CAREGIVER", {"message": message})
        if contacts and key == "med_deflect":
            return out(r["med_deflect_named"].format(name=contacts[0]["name"]), wait=True)
        return out(r[key], wait=True)

    def _medicine_action(
        self, uid: int, text: str, intent: str, lang: str, out: Callable[..., TurnResult]
    ) -> TurnResult:
        r = rp.R[rp.lang_or_default(lang)]
        due = self.core.due_medicines(uid)["current"]
        if not due:
            return out(r["med_none_due"])
        said = set(normalize(text).split(" "))
        named = [d for d in due if said & set(normalize(d["name"]).split(" "))]
        if len(named) == 1:
            target = named[0]
        elif not named and len(due) == 1:
            target = due[0]  # still verified by a spoken yes/no below
        else:
            names = ", ".join(d["name"] for d in (named or due))
            return out(r["med_which"].format(names=names))
        if intent == "MED_TAKEN":
            self.core.propose(uid, "MEDICINE_TAKEN", {"dose_id": target["id"]})
            return out(r["confirm_taken"].format(name=target["name"], dose=target["dose"]), wait=True)
        try:
            self.core.propose(uid, "MEDICINE_SNOOZE", {"dose_id": target["id"]})
        except CoreError as exc:
            if exc.status != 409:
                raise
            self.core.propose(
                uid, "REQUEST_CAREGIVER", {"message": "Aaji kept putting off a medicine reminder."}
            )
            return out(r["med_no_more_snooze"], wait=True)
        return out(r["confirm_snooze"], wait=True)

    def _chat_reply(self, uid: int, text: str, lang: str, now: datetime | None = None) -> str:
        now = now or self.clock()
        reply: str | None = None
        if self.evon is not None and self._llm_remaining() >= _MIN_LLM_BUDGET_S:
            recent = self._recent_history(uid, now)
            interests = self.core.user(uid).get("interests") or []
            raw = self.evon.companion_reply(
                text, lang, now, history=[(role, said) for _, role, said in recent], interests=interests,
                timeout=self._llm_remaining(),
            )
            # two sentences at most, and no boundary broken (human / missed you / medical / recipes, facts)
            reply, reasons = sanitize_companion(raw, lang)
            if raw and reasons:
                log.warning("companion reply rejected (%s); using the fixed line", ",".join(reasons))
        if reply is None:
            n = self._chat_counter.get(uid, 0)
            self._chat_counter[uid] = n + 1
            options = rp.CHAT[rp.lang_or_default(lang)]
            reply = options[n % len(options)]
        turns = self._recent_history(uid, now)
        turns += [(now, "user", text), (now, "assistant", reply)]
        self._history[uid] = turns[-self._history_cap:]
        return reply

    def _recent_history(self, uid: int, now: datetime) -> list[tuple[datetime, str, str]]:
        turns = self._history.get(uid, [])
        if turns and now - turns[-1][0] > _HISTORY_IDLE:
            turns = []
        return list(turns)

    def _distress(self, uid: int, lang: str, trace: dict[str, Any], t0: float) -> TurnResult:
        return self._safety(uid, lang, trace, t0, kind="distress")

    def _safety(
        self, uid: int, lang: str, trace: dict[str, Any], t0: float, kind: str
    ) -> TurnResult:
        """Shared path for distress and physical emergency: stop everything, clear pending actions,
        record the event (core-api alerts family only per consent - emergency policy is PENDING a
        decision by the team), and speak the fixed template."""
        self._drafts.pop(uid, None)
        self._history.pop(uid, None)  # the story stops; nothing resumes after a crisis
        # Every core call is best-effort: the spoken safety reply below is returned regardless.
        try:
            pending = self.core.pending(uid)
            if pending is not None:  # a stray "yes" must not execute anything after distress
                self.core.reject(uid, pending["id"])
        except (CoreError, httpx.HTTPError) as exc:
            log.error("%s: could not clear pending action: %s", kind, exc)
        try:
            self.core.distress(uid)  # core-api alerts caregiver ONLY if consent is configured
        except (CoreError, httpx.HTTPError) as exc:
            log.error("%s: could not record event / alert caregiver: %s", kind, exc)
        r = rp.R[rp.lang_or_default(lang)]
        intent = "EMERGENCY" if kind == "emergency" else "DISTRESS"
        return TurnResult(r[kind], intent, "safety", lang, trace=self._t(trace, t0), screen="safety")

    @staticmethod
    def _t(trace: dict[str, Any], t0: float) -> dict[str, Any]:
        trace["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return trace
