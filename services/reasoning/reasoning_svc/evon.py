"""Client for self-hosted Evon (OpenAI-compatible vLLM/SGLang endpoint).

Contract: strict JSON out, validated against shared/schemas/intent.json. Invalid JSON or schema
failure -> retry once -> caller falls back to the rule-based parser. The LLM never writes to the DB.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import jsonschema

from . import config

_LANG_NAMES = {"mr": ("Marathi", "Devanagari"), "hi": ("Hindi", "Devanagari"), "en": ("English", "Latin")}


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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.http = http or httpx.Client(timeout=20.0, headers=headers)
        self.schema = schema or load_intent_schema()
        self.send_template_kwargs = send_template_kwargs

    def _chat(self, messages: list[dict[str, str]], temperature: float, **extra: Any) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            **extra,
        }
        if self.send_template_kwargs:
            # reasoning traces add latency in the live voice path
            body["chat_template_kwargs"] = {"enable_thinking": False}
        r = self.http.post(f"{self.base_url}/chat/completions", json=body)
        r.raise_for_status()
        return str(r.json()["choices"][0]["message"]["content"])

    def extract_intent(
        self, text: str, language: str, now: datetime, wake: str, lunch: str, dinner: str
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
            f"You are Arjun, an AI companion (not a human) talking with an elderly person in "
            f"{lang_name} using {script} script. Reply in at most two short, warm sentences. Listen "
            f"more than you talk: react briefly and ask one gentle question about their story. "
            f"Never give advice, medical information, recipes, facts or news. Never claim to be "
            f"human or to have feelings, a body, family or experiences. Build on what they said "
            f"earlier in this conversation (shown below) so it feels like one conversation, but "
            f"never refer to anything from another day. Do not repeat a question you already "
            f"asked. {clock}"
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
                top_p=config.COMPANION_TOP_P,
                max_tokens=120,
            )
        except (httpx.HTTPError, ValueError, KeyError):
            return None
        return out.strip() or None
