"""Client for self-hosted Evon (OpenAI-compatible vLLM/SGLang endpoint).

Contract: strict JSON out, validated against shared/schemas/intent.json. Invalid JSON or schema
failure -> retry once -> caller falls back to the rule-based parser. The LLM never writes to the DB.
"""

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import jsonschema

from . import config

log = logging.getLogger("arjun.llm")

_LANG_NAMES = {
    "mr": ("Marathi", "Devanagari"),
    "hi": ("Hindi", "Devanagari"),
    "en": ("English", "Latin"),
}


# ---- what the companion may NOT say: a safety net on top of the prompt (boundaries 4, 5, 9, 10) -------
_VIOLATIONS: dict[str, re.Pattern[str]] = {
    # claims to be human, or to have a family / body
    "human": re.compile(
        r"\b(i am|i'm|im)\s+(a\s+)?(real\s+)?(human|person|man|woman|boy|girl)\b"
        r"|मी\s+(एक\s+)?(खरा\s+)?(माणूस|मनुष्य|इंसान|आदमी)\s+(आहे|आहेत|हूँ|हूं)"
        r"|मैं\s+(एक\s+)?(इंसान|इन्सान|आदमी)\s+(हूँ|हूं)"
        r"|\bmy\s+(wife|husband|son|daughter|mother|father|family)\b"
        r"|माझी\s+(बायको|आई|मुलगी|बहीण)|माझा\s+(मुलगा|भाऊ|नवरा)",
        re.IGNORECASE,
    ),
    # engagement tricks: "I missed you", guilt
    "missed_you": re.compile(
        r"\bi\s+(have\s+)?(really\s+)?miss(ed)?\s+you\b|\bmissing\s+you\b"
        r"|(तुमची|तुझी|आपकी|तुम्हारी)\s*(खूप\s*|बहुत\s*)?(आठवण|याद)",
        re.IGNORECASE,
    ),
    # medical advice: doses, "take the tablet", numbers with units
    "medical": re.compile(
        r"\b\d+(\.\d+)?\s*(mg|ml|mcg)\b"
        r"|(गोळी|गोळ्या|औषध|औषधं|दवा|दवाई|टॅबलेट)\s*(घ्या|घे|घेत|खा|लो|खाओ|बंद|वाढवा)"
        r"|\b(take|taking|stop|skip|double)\b.{0,25}\b(tablet|tablets|pill|pills|medicine|medication|dose)\b"
        r"|\byou\s+should\s+(take|stop)\b"
        # health advice (task C, boundary 5): rest, water, a pill, a doctor visit - in Marathi, Hindi and English.
        # Pointing to a person ("डॉक्टरांना विचारा", "ask your doctor") is allowed; telling her what to DO is not.
        r"|पडून\s+रा[हह]\S*|झोपून\s+रा[हह]\S*|विश्रांती\s+(?:घ्या|घे)\S*|आराम\s+(?:करा|कर|घ्या|कीजिए|कीजिये|करें|करो)"
        r"|पाणी\s+(?:प्या|पी)\S*|पानी\s+(?:पी|पि)\S*"
        r"|(?:दवा|दवाई|गोली)\s+(?:ले|लें|लीजिए|खा)\S*"
        r"|डॉक्टर(?:कडे|ांकडे|च्याकडे)\s+(?:\S+\s+)?जा(?:\S*)"
        r"|डॉक्टर\s+(?:के\s+पास|को)\s+(?:\S+\s+)?(?:जा|दिखा|मिल)\S*"
        r"|\b(?:you\s+should|please|try\s+to|better)\s+(?:\w+\s+)?(?:rest|lie\s+down)\b|\blie\s+down\b|\btake\s+(?:a|some)\s+rest\b"
        r"|\bdrink\s+(?:some\s+|a\s+glass\s+of\s+|plenty\s+of\s+)?water\b|\bstay\s+hydrated\b"
        r"|\b(?:go|see|visit|consult)\s+(?:and\s+)?(?:see\s+)?(?:a|your|the)\s+(?:doctor|hospital)\b",
        re.IGNORECASE,
    ),
    # recipes and facts from memory (the companion asks to be taught instead)
    "recipe_fact": re.compile(
        r"साहित्य|कृती|शिजवा|चमचा|\bingredients?\b|\brecipe\b|\btablespoons?\b|\bteaspoons?\b"
        r"|राजधानी|लोकसंख्या|\bcapital\s+of\b|\bwas\s+born\s+in\b|\bpopulation\b",
        re.IGNORECASE,
    ),
}
_MAX_REPLY_CHARS = 300


def companion_violations(text: str, language: str) -> list[str]:
    """Names of the boundaries a companion reply breaks (empty = fine). Heuristic, not a proof."""
    reasons = [name for name, rx in _VIOLATIONS.items() if rx.search(text)]
    if language in ("mr", "hi") and not any("\u0900" <= ch <= "\u097f" for ch in text):
        reasons.append("script")  # asked for Devanagari, got Latin
    if len(text) > _MAX_REPLY_CHARS:
        reasons.append("too_long")
    return reasons


def sanitize_companion(text: str | None, language: str) -> tuple[str | None, list[str]]:
    """Keep at most two sentences, then reject the reply if it breaks a boundary."""
    if not text or not text.strip():
        return None, ["empty"]
    sentences = re.split(r"(?<=[.?!।])\s+", text.strip())
    cut = " ".join(sentences[:2]).strip()
    reasons = companion_violations(cut, language)
    return (None, reasons) if reasons else (cut, [])


# ---- Sarvam "thinking" output -------------------------------------------------------------------------------
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_thinking(text: str | None) -> str | None:
    """Drop reasoning traces ("<think>...</think>") so they are never spoken or shown. An unclosed <think>
    means the answer never came (max_tokens used up by reasoning): nothing usable."""
    if text is None:
        return None
    out = _THINK.sub("", text)
    if re.search(r"<think>", out, re.IGNORECASE):
        return None
    out = re.sub(r"</think>", "", out, flags=re.IGNORECASE)  # a stray closing tag
    return out.strip() or None


# ---- Timbre v3.0 voice tags (the LLM chooses them; only the allowed gentle ones survive) ---------------------
_TAG = re.compile(r"<\s*([a-z][a-z ]{1,20})\s*>", re.IGNORECASE)


def split_voice_tags(text: str, allowed: tuple[str, ...] = config.VOICE_TAGS, max_tags: int = 2) -> tuple[str, str]:
    """(clean text for the screen and the boundary checks, text for TTS with at most `max_tags` allowed tags).

    Tags are case-sensitive for Timbre, so they are normalised to the exact allowed spelling; anything else in
    angle brackets is removed from both."""
    ok = {t[1:-1].lower(): t for t in allowed}
    kept = 0

    def spoken(mt: re.Match[str]) -> str:
        nonlocal kept
        tag = ok.get(mt.group(1).strip().lower())
        if tag and kept < max_tags:
            kept += 1
            return tag + " "
        return ""

    clean = re.sub(r"\s{2,}", " ", _TAG.sub("", text)).strip()
    voice = re.sub(r"\s{2,}", " ", _TAG.sub(spoken, text)).strip()
    return clean, voice


class LlmBusy(httpx.TransportError):
    """Not sent: over the concurrency / per-minute limit, or the provider said 429 recently. Rules answer."""


class Limiter:
    """Concurrency (at most N calls in flight) + rate (at most M per minute) + backoff after a provider 429.

    Never waits: in a voice turn a queued LLM call is worse than the rules' answer now."""

    def __init__(self, max_concurrent: int = 4, per_minute: int = 60, clock: Any = time.monotonic) -> None:
        import threading

        self._sem = threading.BoundedSemaphore(max(1, max_concurrent))
        self.per_minute, self.clock = per_minute, clock
        self._calls: list[float] = []
        self._cool_until = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        now = self.clock()
        with self._lock:
            if now < self._cool_until:
                raise LlmBusy("provider asked us to slow down")
            self._calls = [t for t in self._calls if now - t < 60.0]
            if len(self._calls) >= self.per_minute:
                raise LlmBusy("per-minute LLM limit reached")
            if not self._sem.acquire(blocking=False):
                raise LlmBusy("too many LLM calls in flight")
            self._calls.append(now)

    def release(self) -> None:
        self._sem.release()

    def cool_down(self, seconds: float) -> None:
        with self._lock:
            self._cool_until = max(self._cool_until, self.clock() + seconds)


MOODS = ("happy", "calm", "neutral", "lonely", "sad", "worried", "unwell", "distressed")
LEVELS = ("normal", "watch", "urgent", "emergency")


def load_intent_schema() -> dict[str, Any]:
    return json.loads((Path(config.SCHEMA_DIR) / "intent.json").read_text(encoding="utf-8"))


class EvonClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        http: httpx.Client | None = None,
        schema: dict[str, Any] | None = None,
        api_key: str = "",
        send_template_kwargs: bool = True,
        provider: str = "evon",
        max_tokens: int = 120,
        timeout_s: float = 4.0,
        reasoning_off: bool = False,
        limiter: Limiter | None = None,
        voice_tags: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.provider = provider
        self.max_tokens = max_tokens
        self.usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}  # running totals for this client
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.http = http or httpx.Client(timeout=timeout_s, headers=headers)
        self.schema = schema or load_intent_schema()
        self.send_template_kwargs = send_template_kwargs
        self.reasoning_off = reasoning_off
        self.limiter = limiter or Limiter()
        self.voice_tags = voice_tags

    def _chat(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        purpose: str = "chat",
        timeout: float | None = None,
        **extra: Any,
    ) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            **extra,
        }
        if self.send_template_kwargs:
            # reasoning traces add latency in the live voice path
            body["chat_template_kwargs"] = {"enable_thinking": False}
        if self.reasoning_off:
            body["reasoning_effort"] = None  # Sarvam: answer directly, no hidden thinking tokens
        t0 = time.perf_counter()
        record: dict[str, Any] = {
            "provider": self.provider,
            "model": self.model,
            "purpose": purpose,
        }
        try:
            self.limiter.acquire()
        except LlmBusy as exc:
            record.update(ok=False, error="LlmBusy", detail=str(exc))
            log.info(json.dumps(record))
            raise
        try:
            r = self.http.post(
                f"{self.base_url}/chat/completions",
                json=body,
                **({"timeout": timeout} if timeout is not None else {}),
            )
            if r.status_code == 429:  # back off; the rules answer until then
                try:
                    wait = float(r.headers.get("retry-after", "30"))
                except ValueError:
                    wait = 30.0
                self.limiter.cool_down(min(max(wait, 1.0), 300.0))
            r.raise_for_status()
            data = r.json()
            finish = data["choices"][0].get("finish_reason")  # "length" = the reply was cut by max_tokens
            content = strip_thinking(data["choices"][0]["message"].get("content"))
            if content is None:
                raise ValueError("no visible answer (only reasoning, or empty)")
        except Exception as exc:
            # one line per call, never the transcript or the reply: provider, model, latency, tokens
            record.update(
                ok=False,
                error=type(exc).__name__,
                latency_ms=round((time.perf_counter() - t0) * 1000),
            )
            log.info(json.dumps(record))
            raise
        finally:
            self.limiter.release()
        usage = data.get("usage") or {}
        self.usage["calls"] += 1
        self.usage["prompt_tokens"] += usage.get("prompt_tokens") or 0
        self.usage["completion_tokens"] += usage.get("completion_tokens") or 0
        record.update(
            ok=True,
            latency_ms=round((time.perf_counter() - t0) * 1000),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            finish_reason=finish,
        )
        log.info(json.dumps(record))
        return content

    def extract_intent(
        self,
        text: str,
        language: str,
        now: datetime,
        wake: str,
        lunch: str,
        dinner: str,
        timeout: float | None = None,
    ) -> dict[str, Any] | None:
        lang_name, script = _LANG_NAMES.get(language, _LANG_NAMES["mr"])
        system = (
            f"You are the intent extractor for Arjun, a voice care companion. The user speaks "
            f"{lang_name} ({script} or romanised). Output ONLY one JSON object matching this "
            f"schema, nothing else: {json.dumps(self.schema)}. "
            f"Today is {now.date().isoformat()}, the current local time is {now:%H:%M}. "
            f"User wake time {wake}, lunch {lunch}, dinner "
            f"{dinner}. Resolve relative dates/times from these. If AM/PM is unclear set "
            f"time_ambiguous=true and time=null. Never invent a task, date or time that was not "
            f"said. Do not give medical advice."
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": text}]
        for _ in range(2):  # initial try + one retry
            try:
                raw = self._chat(
                    messages,
                    config.EXTRACTION_TEMPERATURE,
                    purpose="intent",
                    timeout=timeout,
                    max_tokens=250,
                    response_format={"type": "json_object"},
                )
                data = json.loads(raw)
                jsonschema.validate(data, self.schema)
                return data  # type: ignore[no-any-return]
            except (httpx.HTTPError, ValueError, KeyError, jsonschema.ValidationError):
                continue
        return None

    def companion_reply(
        self,
        text: str,
        language: str,
        now: datetime | None = None,
        history: list[tuple[str, str]] | None = None,
        interests: list[str] | None = None,
        timeout: float | None = None,
    ) -> str | None:
        """`history` is this conversation's earlier (role, text) turns, oldest first; never older."""
        lang_name, script = _LANG_NAMES.get(language, _LANG_NAMES["mr"])
        clock = (
            f"The current local time is {now:%H:%M} on {now:%A}; mention it only if the user asks "
            f"about the time or day. "
            if now
            else ""
        )
        system = (
            f"You are Arjun, an AI voice companion (not a human) talking with an elderly person. "
            f"Always answer in {lang_name}, written in {script} script, the way they speak. "
            f"Reply in at most two short, warm sentences. Listen more than you talk: react briefly, "
            f"then ask ONE gentle follow-up question about what they just said. "
            f"Never give medical advice, a diagnosis, or anything about medicines or doses; if asked, "
            f"say you cannot advise and suggest asking their doctor or family. "
            f"Never recite recipes, facts, news or history from your own knowledge: if asked, say "
            f"you would love to learn it from them and ask them to teach you. "
            f"Never claim to be human, or to have feelings, a body, a family or experiences. "
            f"Never say you missed them, never make them feel guilty for being away, and never "
            f"discourage them from talking to their family or friends. "
            f"Build on what they said earlier in this conversation (shown below), but never refer "
            f"to anything from another day. Do not repeat a question you already asked. {clock}"
        )
        if self.voice_tags:
            system += (
                "Your reply is spoken aloud. When it truly fits the moment, you may put ONE voice tag right "
                f"before the words it should colour, chosen from exactly: {' '.join(config.VOICE_TAGS)}. "
                "For example <laugh> after something funny she said, <slow> for something important, <sigh> "
                "when she shares something sad. Most replies need no tag. Never invent other tags. "
            )
        if interests:
            system += (
                f"Things they enjoy talking about: {', '.join(interests[:3])}. You may ask them to "
                f"tell you about one of these, but never say anything about it yourself; ask them "
                f"to teach you instead. "
            )
        messages = [{"role": "system", "content": system}]
        messages += [{"role": role, "content": content} for role, content in (history or [])]
        messages.append({"role": "user", "content": text})
        try:
            out = self._chat(
                messages,
                config.COMPANION_TEMPERATURE,
                purpose="companion",
                timeout=timeout,
                top_p=config.COMPANION_TOP_P,
                max_tokens=self.max_tokens,
            )
        except (httpx.HTTPError, ValueError, KeyError):
            return None
        return out.strip() or None


    def summarize_conversation(
        self, turns: list[tuple[str, str]], language: str, timeout: float | None = 10.0
    ) -> dict[str, Any] | None:
        """For the family dashboard: {"summary", "mood", "severity", "topics"}. None on any failure.

        Runs after the conversation ended (never in the voice path). The summary is a short English paraphrase:
        no quotes, no medical judgement, nothing invented. The caller keeps a rules floor for severity."""
        if not turns:
            return None
        lines = "\n".join(f"{'Elder' if who == 'user' else 'Arjun'}: {said}" for who, said in turns[-40:])
        system = (
            "You write a short note for the family of an elderly person about one conversation she had with "
            "Arjun, an AI voice companion. Output ONLY one JSON object: "
            '{"summary": string (English, at most 2 short sentences, what she talked about and how she seemed; '
            "paraphrase, never quote her; report only what she said, never diagnose, never guess causes, never "
            'give advice), "mood": one of ' + json.dumps(list(MOODS)) + ', "severity": one of '
            + json.dumps(list(LEVELS)) + ' (normal = ordinary chat; watch = lonely, sad, worried, a complaint '
            "worth a call today; urgent = asked for help, very upset, pain; emergency = chest pain, a fall, "
            'cannot breathe, bleeding), "topics": up to 4 short English words}.'
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": lines}]
        for _ in range(2):
            try:
                raw = self._chat(messages, config.EXTRACTION_TEMPERATURE, purpose="summary", timeout=timeout,
                                 max_tokens=220, response_format={"type": "json_object"})
                data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
                if data.get("mood") not in MOODS or data.get("severity") not in LEVELS:
                    raise ValueError("bad enum")
                summary = str(data.get("summary") or "").strip()[:400]
                topics = [str(t)[:30] for t in (data.get("topics") or [])][:4]
                return {"summary": summary, "mood": data["mood"], "severity": data["severity"], "topics": topics}
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                continue
        return None
