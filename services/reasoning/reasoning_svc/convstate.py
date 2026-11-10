"""Per-user compact CONVERSATION STATE (2026-11-10): what the talk is about right now, so a short "हो", "तेच", "आणखी" or "त्याला"
is answered in context. Rules only (no LLM), in memory only, never stored.

What it holds: current_topic, entities (people / places / times; a medicine is only a flag, boundary 6: no medicine name ever enters
session text), the last 6 exchanges, and (at prompt time) the references in her NEW sentence that point back ("त्याला" -> the last
person named). The pending question stays in SessionMemory (its single owner); `render` points at it.

`fit_prompt` builds the variable part of the prompt in a FIXED order under a token cap. Order of priority (last dropped first):
  1. the open question + the last 2 exchanges   (never dropped)
  2. the state block (topic, entities, references)
  3. the older exchanges up to 6
  4. the facts, best first (top-k shrinks)
  5. today's data / profile context
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from .memory import _stems, norm, overlap

LAST_TURNS = 6  # exchanges
MAX_ENTITIES = 6

_RELATIONS = {
    "नातू": "grandson", "नातवा": "grandson", "नात": "granddaughter", "नातीच": "granddaughter", "नातीला": "granddaughter",
    "पोता": "grandson", "पोती": "granddaughter", "नाती": "granddaughter", "मुलगा": "son", "मुलाला": "son", "मुलाचा": "son",
    "मुलगी": "daughter", "मुलीला": "daughter", "मुलीचा": "daughter", "सून": "daughter-in-law", "सुनेला": "daughter-in-law",
    "जावई": "son-in-law", "नवरा": "husband", "बायको": "wife", "भाऊ": "brother", "भावाला": "brother", "बहीण": "sister",
    "बहिणीला": "sister", "आई": "mother", "बाबा": "father", "बेटा": "son", "बेटी": "daughter", "बेटे": "son", "बहू": "daughter-in-law",
    "डॉक्टर": "doctor", "डॉक्टरांना": "doctor", "डॉक्टरकडे": "doctor", "ड़ॉक्टर": "doctor", "doctor": "doctor", "grandson": "grandson",
    "granddaughter": "granddaughter", "son": "son", "daughter": "daughter", "wife": "wife", "husband": "husband", "brother": "brother",
    "sister": "sister", "mother": "mother", "father": "father", "neighbour": "neighbour", "शेजारी": "neighbour", "मैत्रीण": "friend",
    "मित्र": "friend", "friend": "friend",
}
_PLACES = (
    "दवाखाना", "दवाखान्यात", "हॉस्पिटल", "हॉस्पिटलमध्ये", "hospital", "मंदिर", "मंदिरात", "temple", "बाजार", "बाजारात", "market", "बाग",
    "बागेत", "garden", "गाव", "गावी", "पुणे", "पुण्याला", "मुंबई", "मुंबईला", "नाशिक", "नागपूर", "दिल्ली", "bank", "बँक", "school",
    "शाळा", "घरी", "dispensary", "clinic", "क्लिनिक",
)
_PLACE_STEMS = {_s[:5] for _s in _PLACES}
_MED = ("औषध", "औषधं", "गोळी", "गोळ्या", "दवा", "दवाई", "medicine", "tablet", "tablets", "इंजेक्शन")
_MED_STEMS = {_s[:4] for _s in _MED}
_TIME_RE = re.compile(
    r"(\d{1,2}(?::\d{2})?\s*(?:वाजता|वाजले|बजे|am|pm|a\.m\.|p\.m\.)|उद्या|आज|काल|परवा|सकाळी|दुपारी|संध्याकाळी|रात्री|सोमवार|मंगळवार|बुधवार|"
    r"गुरुवार|शुक्रवार|शनिवार|रविवार|tomorrow|today|yesterday|tonight|morning|evening)", re.IGNORECASE,
)
# "हो / नाही / तेच / आणखी / बरं": a short answer that only means something next to the question before it
SHORT_ANSWERS = frozenset({
    "हो", "होय", "हां", "हाँ", "जी", "ठीक", "बरं", "बरं का", "नाही", "नको", "नही", "तेच", "तीच", "तोच", "आणखी", "अजून", "पुन्हा", "परत",
    "और", "फिर", "वही", "वही वाला", "yes", "no", "ok", "okay", "same", "more", "again", "that one", "sure", "ho", "nahi", "nako", "teech",
    "aankhi", "ajun", "ho ho", "हो हो", "हो ना", "बरोबर", "सही", "बस",
})
_PRONOUNS = frozenset({
    "तो", "ती", "ते", "त्याला", "तिला", "त्यांना", "त्याचं", "त्याचे", "त्याचा", "तिचं", "तिचे", "तिचा", "त्यांचं", "त्यांचा", "त्याच्याशी",
    "तिच्याशी", "त्याच्याबद्दल", "तिच्याबद्दल", "वो", "उसको", "उसे", "उसका", "उसकी", "उनको", "उनका", "उससे", "he", "she", "him", "her", "his",
    "they", "them", "it", "तेही", "त्यालाही",
})
_FUNCTION = frozenset({
    "आहे", "आहेत", "का", "की", "आणि", "पण", "हा", "ही", "हे", "या", "त्या", "ला", "ने", "चा", "ची", "चे", "चं", "साठी", "मला", "मी", "तुम्ही",
    "आज", "उद्या", "काल", "आता", "खूप", "काय", "कसा", "कशी", "कसे", "कुठे", "केव्हा", "the", "a", "is", "and", "my", "to", "of", "with",
})
_WORD = re.compile(r"[\wऀ-ॿ]+")


def est_tokens(text: str) -> int:
    """A cheap, slightly pessimistic token estimate for Devanagari / Latin mixes (no tokenizer in the process)."""
    return max(len(text) // 3, int(len(text.split()) * 1.6)) if text else 0


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text)


def is_short_answer(text: str) -> bool:
    n = norm(text)
    return bool(n) and (n in SHORT_ANSWERS or (len(n.split()) <= 2 and all(w in SHORT_ANSWERS for w in n.split())))


def extract_entities(text: str, known_names: tuple[str, ...] = ()) -> dict[str, list[str]]:
    """people (relation + name), places, times, and a medicine FLAG (never a name). Rules only."""
    toks = _tokens(text)
    low = [t.lower() for t in toks]
    people: list[str] = []
    for i, t in enumerate(toks):
        rel = _RELATIONS.get(t) or _RELATIONS.get(low[i]) or next((v for k, v in _RELATIONS.items() if len(k) >= 4 and t.startswith(k) and len(t) <= len(k) + 3), None)
        if not rel:
            continue
        name = ""
        if i + 1 < len(toks):
            nxt = toks[i + 1]
            if nxt not in _FUNCTION and nxt.lower() not in _RELATIONS and nxt not in SHORT_ANSWERS and len(nxt) >= 3 and (nxt[0].isupper() or "ऀ" <= nxt[0] <= "ॿ") and nxt not in _PRONOUNS:
                name = nxt
        people.append(f"{rel} {name}".strip() if name else rel)
    for n in known_names:
        if n and n in text and not any(n in p for p in people):
            people.append(n)
    meds = ["medicine"] if any(t[:4] in _MED_STEMS or t.lower() in _MED for t in toks) else []
    for t in toks:  # a Latin capitalised word that is not a sentence start: a name (NOT in a medicine sentence: it may be the drug's name)
        if not meds and t[0].isascii() and t[0].isupper() and t.lower() not in _RELATIONS and t != toks[0] and not any(t in p for p in people):
            people.append(t)
    places = [t for t in toks if t[:5] in _PLACE_STEMS or t.lower() in _PLACES]
    times = [m.group(0).strip() for m in _TIME_RE.finditer(text)]
    return {
        "people": _uniq(people)[:MAX_ENTITIES], "places": _uniq(places)[:MAX_ENTITIES],
        "times": _uniq(times)[:MAX_ENTITIES], "medicines": meds,
    }


def _uniq(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def topic_phrase(text: str, ents: dict[str, list[str]]) -> str:
    if ents["medicines"]:
        return "a medicine"  # boundary 6: no medicine name in any session text
    named = [*ents["people"][:1], *ents["places"][:1]]
    if named:
        return " / ".join(named)
    words = [w for w in _tokens(text) if w not in _FUNCTION and w not in _PRONOUNS and w not in SHORT_ANSWERS and len(w) > 1]
    return " ".join(words[:5])


@dataclass
class ConvState:
    topic: str = ""
    prev_topic: str = ""
    people: list[str] = field(default_factory=list)  # most recent LAST
    places: list[str] = field(default_factory=list)
    times: list[str] = field(default_factory=list)
    medicine_talk: bool = False  # a flag only
    turns: list[tuple[str, str]] = field(default_factory=list)  # (said, replied), at most LAST_TURNS
    updated: datetime | None = None


class StateTracker:
    def __init__(self, idle_min: float = 30.0) -> None:
        self._s: dict[int, ConvState] = {}
        self.idle_s = idle_min * 60

    def get(self, uid: int) -> ConvState:
        return self._s.setdefault(uid, ConvState())

    def reset(self, uid: int) -> None:
        self._s.pop(uid, None)

    def update(self, uid: int, now: datetime, said: str, reply: str, known_names: tuple[str, ...] = ()) -> ConvState:
        """Called once per spoken exchange (after the reply is final). Follows her when the subject changes."""
        st = self.get(uid)
        if st.updated is not None and (now - st.updated).total_seconds() > self.idle_s:
            self._s[uid] = st = ConvState()  # a new conversation after a long silence
        ents = extract_entities(said, known_names)
        for key, attr in (("people", "people"), ("places", "places"), ("times", "times")):
            cur = getattr(st, attr)
            for e in ents[key]:
                if e in cur:
                    cur.remove(e)
                cur.append(e)  # most recent last
            del cur[:-MAX_ENTITIES]
        st.medicine_talk = bool(ents["medicines"]) or (st.medicine_talk and is_short_answer(said))
        substantive = not is_short_answer(said) and len(_tokens(said)) >= 3
        if substantive:
            new = topic_phrase(said, ents)
            if new and (not st.topic or overlap(new, st.topic) < 0.2):
                st.prev_topic, st.topic = st.topic, new  # she changed the subject: follow her
        st.turns.append((said.strip()[:300], reply.strip()[:300]))
        del st.turns[:-LAST_TURNS]
        st.updated = now
        return st

    def scrub(self, uid: int, fact: str) -> None:
        """She said "forget this": the topic, entities and turns that carry those words leave the state too."""
        st = self._s.get(uid)
        if st is None:
            return
        words = _stems(fact)

        def hit(t: str) -> bool:
            return len(_stems(t) & words) >= 2 or overlap(t, fact) >= 0.4

        st.turns = [(a, b) for a, b in st.turns if not hit(a)]
        if hit(st.topic):
            st.topic = ""
        if hit(st.prev_topic):
            st.prev_topic = ""
        for attr in ("people", "places", "times"):
            setattr(st, attr, [e for e in getattr(st, attr) if not (_stems(e) & words)])

    def references(self, uid: int, text: str) -> list[str]:
        """What a pronoun / short answer in HER NEW sentence most likely points back to (computed before update)."""
        st = self._s.get(uid)
        if st is None:
            return []
        toks = _tokens(text)
        out: list[str] = []
        pron = [t for t in toks if t in _PRONOUNS or t.lower() in _PRONOUNS]
        if pron:
            if st.people:
                out.append(f'"{pron[0]}" most likely means: {st.people[-1]} (the last person you were talking about)')
            elif st.topic:
                out.append(f'"{pron[0]}" may mean the current topic "{st.topic}"; if that does not fit, ask ONE short question quoting her word')
            else:
                out.append(f'"{pron[0]}" has nothing before it to point at: ask ONE short question, quoting her word')
        if is_short_answer(text):
            out.append(f'"{text.strip()[:20]}" is a SHORT ANSWER: it answers your last question / offer, nothing else')
        return out

    def block(self, uid: int, text: str) -> str:
        st = self._s.get(uid)
        refs = self.references(uid, text)
        if (st is None or not (st.topic or st.people or st.places or st.times)) and not refs:
            return ""
        lines = ["CONVERSATION STATE (what the talk is about right now; answer inside it, never recite it):"]
        if st is not None:
            if st.topic:
                lines.append(f"- current topic: {st.topic}" + (f" (before that: {st.prev_topic})" if st.prev_topic else ""))
            if st.people:
                lines.append("- people mentioned: " + ", ".join(st.people[-4:]))
            if st.places:
                lines.append("- places mentioned: " + ", ".join(st.places[-3:]))
            if st.times:
                lines.append("- times mentioned: " + ", ".join(st.times[-3:]))
            if st.medicine_talk:
                lines.append("- she is talking about a medicine: say nothing about it yourself; the family and the doctor decide")
        lines += [f"- {r}" for r in refs]
        return "\n".join(lines) + "\n"


# ---- the fixed-order, capped prompt ------------------------------------------------------------------------------
def fit_prompt(
    *,
    messages: list[tuple[str, str]],
    block_memory: str,
    block_state: str,
    context_base: str,
    facts: list[str],
    facts_header: str,
    cap_tokens: int,
    keep_messages: int = LAST_TURNS * 2,
    protected_messages: int = 4,
) -> tuple[list[tuple[str, str]], str, str, dict[str, int]]:
    """-> (history messages, memory block, context string, info). Never drops `block_memory` (it carries the open question) or the
    last `protected_messages` messages (2 exchanges). Order of dropping when over `cap_tokens`: facts (one at a time, last first),
    older messages down to the protected ones, then the state block shrinks to its first lines. context_base is kept whole."""
    msgs = list(messages)[-keep_messages:]
    while msgs and msgs[0][0] != "user":
        msgs.pop(0)  # history must start with her
    facts = list(facts)
    state = block_state

    def render() -> tuple[str, int]:
        ctx = context_base + (("\n" + facts_header + "\n" + "\n".join(facts)) if facts else "")
        total = est_tokens(ctx) + est_tokens(block_memory) + est_tokens(state) + sum(est_tokens(t) for _, t in msgs)
        return ctx, total

    ctx, total = render()
    dropped = {"facts": 0, "messages": 0, "state_lines": 0}
    while total > cap_tokens and facts:
        facts.pop()
        dropped["facts"] += 1
        ctx, total = render()
    while total > cap_tokens and len(msgs) > protected_messages:
        msgs.pop(0)
        while msgs and msgs[0][0] != "user":
            msgs.pop(0)
        dropped["messages"] += 1
        ctx, total = render()
    lines = state.splitlines()
    while total > cap_tokens and len(lines) > 3:
        lines.pop()  # the references are last: the topic line outlives the rest
        state = "\n".join(lines) + "\n"
        dropped["state_lines"] += 1
        ctx, total = render()
    return msgs, block_memory + state, ctx, {"tokens": total, **dropped}
