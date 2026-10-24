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
        r"|\b(take|stop|skip|double)\b.{0,25}\b(tablet|tablets|pill|pills|medicine|medication|dose)\b"
        r"|\byou\s+should\s+(take|stop)\b",
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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.provider = provider
        self.max_tokens = max_tokens
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.http = http or httpx.Client(timeout=timeout_s, headers=headers)
        self.schema = schema or load_intent_schema()
        self.send_template_kwargs = send_template_kwargs

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
        t0 = time.perf_counter()
        record: dict[str, Any] = {
            "provider": self.provider,
            "model": self.model,
            "purpose": purpose,
        }
        try:
            r = self.http.post(
                f"{self.base_url}/chat/completions",
                json=body,
                **({"timeout": timeout} if timeout is not None else {}),
            )
            r.raise_for_status()
            data = r.json()
            content = str(data["choices"][0]["message"]["content"])
        except Exception as exc:
            # one line per call, never the transcript or the reply: provider, model, latency, tokens
            record.update(
                ok=False,
                error=type(exc).__name__,
                latency_ms=round((time.perf_counter() - t0) * 1000),
            )
            log.info(json.dumps(record))
            raise
        usage = data.get("usage") or {}
        record.update(
            ok=True,
            latency_ms=round((time.perf_counter() - t0) * 1000),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
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
