"""Arjun's memory: THIS SESSION (turns, a running summary, open question) and HER LIFE (facts from core-api).

Two layers, both small and both private:

  SessionMemory   in memory only. One history per user that records EVERY spoken line: what she said, what Arjun
                  answered (rules, tools, safety, LLM), and what Arjun said on his own (check-ins, reminders).
                  Keeps the last SESSION_EXCHANGES exchanges; older turns, and a whole conversation after a long
                  silence, are COMPRESSED into a 3-line running summary instead of being deleted. It also holds the
                  question Arjun is waiting for an answer to, and the questions already asked today.

  FactBook        a cached view of core-api's user_facts (the durable "long-term memory"). The facts most relevant to
                  the sentence she just said go into every LLM call's USER CONTEXT.

The LLM never writes either layer by itself: reasoning records what was really said (boundary 1), and core-api
validates and stores facts (facts.py). Medicine names, doses and readings never enter the session memory as text
(boundary 6): only a neutral note that something happened.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

SUMMARY_LINES = 3
SUMMARY_LINE_CHARS = 170
MAX_EVENTS = 8
SESSION_FORGET_AFTER = timedelta(hours=24)  # a day later only the long-term facts remain
PENDING_TTL = timedelta(minutes=10)
FACT_TOUCH_GAP = timedelta(minutes=10)

_SENTENCE = re.compile(r"[^।.!?]+[।.!?]*")


@dataclass
class Turn:
    at: datetime
    role: str  # "user" | "assistant"
    text: str
    kind: str = "chat"  # chat | care | checkin | reminder | safety | action


@dataclass
class Session:
    turns: list[Turn] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)
    events: list[tuple[datetime, str]] = field(default_factory=list)  # what the APP did (never her words)
    last_at: datetime | None = None
    pending: tuple[datetime, str, str] | None = None  # (asked at, the question, kind)
    asked: list[tuple[datetime, str]] = field(default_factory=list)
    safety_at: datetime | None = None


@dataclass
class MemoryView:
    messages: list[tuple[str, str]]  # strictly alternating (role, text), user first: what the LLM sees as history
    block: str  # text for the system prompt: summary, app events, open question, questions asked today
    turns: list[Turn]


def last_question(text: str) -> str:
    """The last sentence of `text` that asks something ("" when none)."""
    found = ""
    for m in _SENTENCE.finditer(text):
        sentence = m.group(0).strip()
        if sentence.endswith("?"):
            found = sentence
    return found[:160]


def norm(text: str) -> str:
    return re.sub(r"[\s,.?!।;:\"“”‘’()\[\]{}-]+", " ", text.lower()).strip()


def _stem(token: str) -> str:
    return token[:4] if len(token) > 4 else token


def _stems(text: str) -> set[str]:
    return {_stem(t) for t in norm(text).split() if len(t) >= 2}


def overlap(a: str, b: str) -> float:
    sa, sb = _stems(a), _stems(b)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


# ---- shaping a companion reply: at most one question, not every reply, never the same one twice a day --------------
def shape_questions(reply: str, asked_today: list[str], previous_was_question: bool) -> str:
    """Keep the FIRST question only; drop it when the previous reply was already a question (so a reply is
    sometimes just warm), or when it repeats a question asked earlier today. A reply that is only a question
    is left as it is (there is nothing warm to keep)."""
    parts = [m.group(0).strip() for m in _SENTENCE.finditer(reply) if m.group(0).strip()]
    questions = [i for i, p in enumerate(parts) if p.endswith("?")]
    if not questions:
        return reply
    drop = set(questions[1:])
    first = questions[0]
    repeated = any(overlap(parts[first], q) >= 0.8 for q in asked_today)
    if previous_was_question or repeated:
        drop.add(first)
    kept = [p for i, p in enumerate(parts) if i not in drop]
    if sum(len(p) for p in kept) < 6:  # nothing warm would be left: keep the first question rather than a stub
        drop.discard(first)
        kept = [p for i, p in enumerate(parts) if i not in drop]
    return " ".join(kept)


# ---- explicit memory commands ---------------------------------------------------------------------------------------
_REMEMBER = (
    "लक्षात ठेवा", "लक्षात ठेव", "लक्षात ठेवशील", "लक्ष्यात ठेव", "remember this", "remember that", "yaad rakh",
    "yaad rakho", "lakshat thev", "lakshat theva",
)
_FORGET = (
    "विसरून जा", "विसरुन जा", "विसरून टाक", "विसरा", "विसर", "forget this", "forget that", "bhool ja", "visarun ja",
    "visar",
)
_FILLER = {"हे", "हें", "ते", "की", "ना", "तू", "तुम्ही", "अर्जुन", "arjun", "कृपया", "please", "ही", "हा", "आणि"}
_WORD_SPLIT = re.compile(r"[\s,।.!?:;]+")


def _words(text: str) -> list[str]:
    return [w for w in _WORD_SPLIT.split(text.strip()) if w]


def _strip_command(text: str, commands: tuple[str, ...]) -> tuple[bool, str]:
    """Find a command phrase as WHOLE WORDS in a row; return (found, the other words without filler)."""
    words = _words(text)
    low = [w.lower() for w in words]
    for phrase in sorted(commands, key=lambda c: -len(c.split())):
        parts = phrase.split()
        for i in range(len(low) - len(parts) + 1):
            if low[i:i + len(parts)] == parts:
                rest = words[:i] + words[i + len(parts):]
                return True, " ".join(w for w in rest if w.lower() not in _FILLER).strip()
    return False, ""


def parse_remember(text: str) -> str | None:
    """"लक्षात ठेव, माझ्या नातवाचं नाव आर्यन" -> the content; "हे लक्षात ठेव" -> "" (the last thing she said); else None."""
    hit, content = _strip_command(text, _REMEMBER)
    return content if hit else None


def parse_forget(text: str) -> str | None:
    """"हे विसरून जा" -> "" (the last fact); "आर्यनचं नाव विसरून जा" -> the words to match; else None."""
    hit, content = _strip_command(text, _FORGET)
    return content if hit else None


# ---- the session ------------------------------------------------------------------------------------------------
class SessionMemory:
    def __init__(self, exchanges: int = 20, idle_min: float = 30.0) -> None:
        self.cap = max(1, exchanges) * 2
        self.idle = timedelta(minutes=idle_min)
        self._s: dict[int, Session] = {}

    # -- plumbing
    def _session(self, uid: int) -> Session:
        return self._s.setdefault(uid, Session())

    def session(self, uid: int) -> Session | None:
        return self._s.get(uid)

    def reset(self, uid: int) -> None:
        self._s.pop(uid, None)

    def _roll(self, s: Session, now: datetime) -> None:
        """A long silence ends the conversation, not the memory: its turns become summary lines."""
        if s.last_at is None:
            return
        gap = now - s.last_at
        if gap > SESSION_FORGET_AFTER:
            s.turns, s.summary, s.events, s.asked, s.pending, s.safety_at = [], [], [], [], None, None
        elif gap > self.idle:
            self._compress(s, len(s.turns))
            s.pending = None

    def _compress(self, s: Session, count: int) -> None:
        old, s.turns = s.turns[:count], s.turns[count:]
        if not old:
            return
        said = [t for t in old if t.role == "user" and len(t.text.split()) >= 3 and t.kind != "care"]
        picked: list[str] = []
        for t in sorted(said, key=lambda t: -len(t.text))[:3]:
            picked.append(t.text.strip()[:70])
        # keep them in the order she said them
        picked.sort(key=lambda p: next((i for i, t in enumerate(old) if t.text.strip().startswith(p)), 0))
        if not picked:
            doing = [t.text for t in old if t.role == "assistant" and t.kind in ("action", "checkin", "reminder")]
            picked = [doing[0][:70]] if doing else []
        if picked:
            span = f"{old[0].at:%d %b %H:%M}"
            s.summary.append(f"{span}: she talked about: " + " | ".join(picked))
        while len(s.summary) > SUMMARY_LINES:  # merge the two oldest lines, keep the line short
            merged = (s.summary[0] + " // " + s.summary[1])[:SUMMARY_LINE_CHARS * 2]
            s.summary = [merged, *s.summary[2:]]
        s.summary = [line[: SUMMARY_LINE_CHARS * 2] for line in s.summary]

    def _trim(self, s: Session) -> None:
        if len(s.turns) > self.cap:
            self._compress(s, len(s.turns) - self.cap)

    # -- writers: every spoken line goes through exactly one of these
    def exchange(self, uid: int, now: datetime, said: str, reply: str, *, kind: str = "chat", limit: int = 0) -> None:
        """She spoke, Arjun answered (by rule, tool, safety template or LLM)."""
        s = self._session(uid)
        self._roll(s, now)
        cut = (lambda x: x.strip()[:limit]) if limit else (lambda x: x.strip())
        s.turns.append(Turn(now, "user", cut(said), kind))
        s.turns.append(Turn(now, "assistant", cut(reply), kind))
        s.last_at = now
        s.pending = None
        q = last_question(reply)
        if q:
            s.pending = (now, q, kind)
            s.asked.append((now, q))
        self._trim(s)

    def arjun_said(self, uid: int, now: datetime, text: str, kind: str) -> None:
        """Arjun spoke first: a check-in, a reminder, an opener."""
        s = self._session(uid)
        self._roll(s, now)
        s.turns.append(Turn(now, "assistant", text.strip(), kind))
        s.last_at = now
        q = last_question(text)
        if q:
            s.pending = (now, q, kind)
            s.asked.append((now, q))
        self._trim(s)

    def event(self, uid: int, now: datetime, text: str) -> None:
        """Something the APP did (never her words, never a medicine name): kept as a short note."""
        s = self._session(uid)
        self._roll(s, now)
        s.events.append((now, text[:120]))
        s.events = s.events[-MAX_EVENTS:]
        s.last_at = now

    def safety(self, uid: int, now: datetime, kind: str) -> None:
        s = self._session(uid)
        s.safety_at = now
        self.event(uid, now, f"safety: {kind} moment; a fixed safety reply was spoken")
        s.pending = None

    def clear_pending(self, uid: int) -> None:
        if uid in self._s:
            self._s[uid].pending = None

    def scrub(self, uid: int, fact: str) -> None:
        """She said "forget this": the turn that carried the fact and its answer leave the session, and the summary."""
        s = self._s.get(uid)
        if s is None:
            return
        keep: list[Turn] = []
        skip_reply = False
        for t in s.turns:
            if t.role == "user" and overlap(t.text, fact) >= 0.4:
                skip_reply = True
                continue
            if t.role == "assistant" and skip_reply:
                skip_reply = False
                continue
            skip_reply = False
            keep.append(t)
        s.turns = keep
        facts = _stems(fact)
        s.summary = [line for line in s.summary if len(_stems(line) & facts) < 2]

    # -- readers
    def pending(self, uid: int, now: datetime) -> tuple[str, str] | None:
        s = self._s.get(uid)
        if s is None or s.pending is None or now - s.pending[0] > PENDING_TTL:
            return None
        return s.pending[1], s.pending[2]

    def asked_today(self, uid: int, now: datetime) -> list[str]:
        s = self._s.get(uid)
        if s is None:
            return []
        return [q for at, q in s.asked if at.date() == now.date()]

    def last_user_text(self, uid: int) -> str:
        s = self._s.get(uid)
        if s is None:
            return ""
        for t in reversed(s.turns):
            if t.role == "user":
                return t.text
        return ""

    def previous_reply_was_question(self, uid: int, now: datetime) -> bool:
        s = self._s.get(uid)
        if s is None or s.last_at is None or now - s.last_at > self.idle:  # a new conversation: nothing came just before
            return False
        for t in reversed(s.turns):
            if t.role == "assistant":
                return t.text.rstrip().endswith("?")
        return False

    def view(self, uid: int, now: datetime) -> MemoryView:
        s = self._s.get(uid)
        if s is None:
            return MemoryView([], "", [])
        self._roll(s, now)
        turns = list(s.turns)
        # an assistant line that opens the history (a check-in Arjun asked first) cannot be the first chat message:
        # it goes into the system block as "you already said", and the alternating messages start with her.
        lead: list[str] = []
        while turns and turns[0].role == "assistant":
            lead.append(turns.pop(0).text)
        messages: list[tuple[str, str]] = []
        for t in turns:
            if messages and messages[-1][0] == t.role:
                messages[-1] = (t.role, messages[-1][1] + "\n" + t.text)
            else:
                messages.append((t.role, t.text))
        lines: list[str] = []
        if s.summary:
            lines.append("Earlier in this session (a short summary of older talk): " + " // ".join(s.summary))
        if lead:
            lines.append("You (Arjun) had already said, before her first line below: " + " ".join(lead[-3:]))
        recent_events = [f"{at:%H:%M} {text}" for at, text in s.events if now - at < timedelta(hours=6)]
        if recent_events:
            lines.append("What the app did for her (not her words; do not read it out): " + "; ".join(recent_events[-5:]))
        if s.safety_at is not None and now - s.safety_at < timedelta(hours=2):
            lines.append(
                f"A safety moment happened at {s.safety_at:%H:%M}. Be gentle and calm; do not joke or start new small "
                "talk; if she raises it, point to her family."
            )
        asked = self.asked_today(uid, now)
        if asked:
            lines.append("Questions you already asked today (never ask the same one again): " + " | ".join(asked[-6:]))
        pend = self.pending(uid, now)
        if pend is not None:
            lines.append(
                f'OPEN QUESTION: you (Arjun) just asked: "{pend[0]}". If her next sentence is short (yes, no, a dish, '
                "a name, a time), it is the ANSWER to this question: take it as that, do not ask what she means."
            )
        block = ("THIS SESSION (your own memory of today; use it naturally, never recite it):\n" + "\n".join(lines)) if lines else ""
        return MemoryView(messages, block, turns)


# ---- her life: the facts ----------------------------------------------------------------------------------------
def days_ago_label(told: str, now: datetime) -> str:
    try:
        days = (now.date() - datetime.fromisoformat(told[:10]).date()).days
    except ValueError:
        return "earlier"
    return "today" if days <= 0 else "yesterday" if days == 1 else f"{days} days ago"


class FactBook:
    """core-api's user_facts for one person, cached for a minute, ranked for the sentence she just said."""

    def __init__(self, core: Any, mono: Any, ttl_s: float = 60.0) -> None:
        self.core, self._mono, self.ttl = core, mono, ttl_s
        self._cache: dict[int, tuple[float, list[dict[str, Any]]]] = {}
        self._touched: dict[int, datetime] = {}

    def invalidate(self, uid: int) -> None:
        self._cache.pop(uid, None)

    def all(self, uid: int) -> list[dict[str, Any]]:
        hit = self._cache.get(uid)
        if hit is not None and self._mono() - hit[0] < self.ttl:
            return hit[1]
        try:
            rows = list(self.core.facts(uid) or [])
        except Exception:  # noqa: BLE001 - no memory is better than no answer
            return hit[1] if hit else []
        self._cache[uid] = (self._mono(), rows)
        return rows

    def relevant(self, uid: int, text: str, now: datetime, limit: int = 10) -> list[tuple[dict[str, Any], bool]]:
        """(fact, matched the sentence?) best first: matches by shared words, then people, then the most recent."""
        facts = self.all(uid)
        if not facts:
            return []
        scored: list[tuple[float, dict[str, Any], bool]] = []
        sentence = _stems(text)
        for f in facts:
            shared = len(sentence & _stems(str(f.get("fact", ""))))
            try:
                age_days = max(0, (now.date() - datetime.fromisoformat(str(f.get("source_date"))[:10]).date()).days)
            except ValueError:
                age_days = 30
            score = shared * 3.0 + (1.5 if f.get("kind") == "person" else 0.0) + max(0.0, 2.0 - age_days * 0.15)
            if f.get("kind") == "event" and age_days <= 2:
                score += 2.0  # something she mentioned very recently: worth a follow-up
            score += float(f.get("confidence") or 0.0) * 0.3
            scored.append((score, f, shared > 0))
        scored.sort(key=lambda x: -x[0])
        return [(f, m) for _, f, m in scored[:limit]]

    def block(self, uid: int, text: str, now: datetime, limit: int = 10) -> str:
        picked = self.relevant(uid, text, now, limit)
        if not picked:
            return ""
        lines = [
            f"- {f.get('fact')} ({f.get('kind')}, she told you {days_ago_label(str(f.get('source_date')), now)})"
            for f, _ in picked
        ]
        self._touch(uid, [f for f, matched in picked if matched][:3], now)
        return (
            "WHAT SHE HAS TOLD YOU ABOUT HER LIFE (true, from earlier days; use a fact only when it fits: call people "
            "by name, ask how an event went, never invent more, never read it as a list):\n" + "\n".join(lines)
        )

    def _touch(self, uid: int, facts: list[dict[str, Any]], now: datetime) -> None:
        last = self._touched.get(uid)
        if not facts or (last is not None and now - last < FACT_TOUCH_GAP):
            return
        self._touched[uid] = now
        for f in facts:
            try:
                self.core.touch_fact(uid, int(f["id"]))
            except Exception:  # noqa: BLE001 - bookkeeping only
                pass
