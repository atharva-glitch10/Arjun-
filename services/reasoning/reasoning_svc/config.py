"""Runtime config. Temperatures are FIXED constants - never changed at runtime."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

EXTRACTION_TEMPERATURE = 0.0  # care mode / intent extraction / distress: always 0
# Lowered 0.6 -> 0.3 (2026-11-02) after long, guessing replies at 0.6. UNVERIFIED with a real voice.
COMPANION_TEMPERATURE = 0.3
COMPANION_TOP_P = 0.95


SARVAM_BASE_URL = "https://api.sarvam.ai/v1"
SARVAM_MODEL = "sarvam-105b"


@dataclass(frozen=True)
class LlmSettings:
    """The one OpenAI-compatible LLM used for open conversation (and messy UNKNOWN phrasing).

    Gnani = Prisma + Timbre. This LLM is a hosted, NON-Gnani provider when LLM_* is set; Evon (self-hosted
    Gnani) is not used for the demo and is only kept working through the EVON_* alias names.
    """

    base_url: str = ""
    model: str = ""
    api_key: str = field(default="", repr=False)  # never printed or logged
    provider: str = "none"
    send_template_kwargs: bool = True
    timeout_s: float = 4.0  # one budget for ALL LLM calls in a turn (the voice path waits ~5 s for reasoning)
    max_tokens: int = 80
    history_exchanges: int = 8  # last eight user/assistant exchanges (task B, 2026-10-31); was 4
    reasoning_off: bool = False  # send reasoning_effort=null (Sarvam): no hidden "thinking" before the answer
    max_concurrent: int = 4  # LLM calls in flight at once (concurrency limit)
    per_minute: int = 60  # LLM calls per minute (rate limit); over it the rules answer instead

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model)


def llm_settings(env: Mapping[str, str] | None = None) -> LlmSettings:
    """LLM_* names win; EVON_* keep working as aliases. The two sets are never mixed: a missing LLM_MODEL
    must not silently become the Evon model name and get sent to a hosted provider."""
    e = os.environ if env is None else env

    def get(name: str) -> str:
        return (e.get(name) or "").strip()

    def number(name: str, default: float, cast: type) -> float:
        try:
            value = cast(get(name))
        except ValueError:
            return default
        return value if value > 0 else default

    if get("LLM_BASE_URL"):
        base, model, key = get("LLM_BASE_URL"), get("LLM_MODEL"), get("LLM_API_KEY")
        provider = get("LLM_PROVIDER_NAME") or "hosted-llm"
    elif get("SARVAM_API_KEY"):
        # Sarvam (hosted, non-Gnani), OpenAI-compatible. Setting SARVAM_API_KEY alone turns it on.
        base = get("SARVAM_BASE_URL") or SARVAM_BASE_URL
        model, key, provider = get("SARVAM_MODEL") or SARVAM_MODEL, get("SARVAM_API_KEY"), "sarvam"
    else:
        base, key = get("EVON_BASE_URL"), get("EVON_API_KEY")
        model = get("EVON_MODEL") or ("gnani/gnani-evon-v3.3-30B-A3B" if base else "")
        provider = get("LLM_PROVIDER_NAME") or ("evon" if base else "none")
    sarvam = provider == "sarvam" or "sarvam.ai" in base
    # chat_template_kwargs is a vLLM/Evon extension; hosted Sarvam does not take it.
    template = get("LLM_SEND_TEMPLATE_KWARGS") or get("EVON_SEND_TEMPLATE_KWARGS") or ("0" if sarvam else "1")
    return LlmSettings(
        base_url=base,
        model=model,
        api_key=key,
        provider=provider,
        send_template_kwargs=template != "0",
        timeout_s=float(number("LLM_TIMEOUT_S", 4.0, float)),
        max_tokens=int(number("LLM_MAX_TOKENS", 80, int)),
        history_exchanges=int(number("LLM_HISTORY_EXCHANGES", 8, int)),
        # Sarvam-105B "thinks" by default; in a voice turn that is pure latency, so it is switched off.
        reasoning_off=sarvam and get("LLM_REASONING") != "1",
        max_concurrent=int(number("LLM_MAX_CONCURRENT", 4, int)),
        per_minute=int(number("LLM_PER_MINUTE", 60, int)),
    )


_S = llm_settings()
# Old names, kept so existing imports and docs keep working.
EVON_BASE_URL = _S.base_url
EVON_MODEL = _S.model
EVON_API_KEY = _S.api_key
EVON_SEND_TEMPLATE_KWARGS = _S.send_template_kwargs
LLM_TIMEOUT_S = _S.timeout_s
LLM_HISTORY_EXCHANGES = _S.history_exchanges
CORE_API_URL = os.environ.get("CORE_API_URL", "http://core-api:8000")
CORE_API_KEY = os.environ.get("CORE_API_KEY", "")
SCHEMA_DIR = os.environ.get(
    "SHARED_SCHEMA_DIR",
    os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared", "schemas")),
)

ELDERLINE_NUMBER = "14567"  # govt senior helpline, 8 AM - 8 PM
LONG_STORY_WORDS = 15  # a CHAT turn at least this long triggers a "keep this story?" consent ask

# No-question mode (default): act at once, read back in one line, "नको" within UNDO_WINDOW_S undoes it.
# ARJUN_ASK_BEFORE_ACTING=1 brings back the old "... ठेवू का? हो किंवा नाही" flow.
ASK_BEFORE_ACTING = os.environ.get("ARJUN_ASK_BEFORE_ACTING", "0") == "1"
UNDO_WINDOW_S = float(os.environ.get("UNDO_WINDOW_S", "150"))  # core-api allows 180 s; keep a margin

# Timbre v3.0 inline voice tags the LLM may choose at runtime. Only gentle ones: no <shouting>, <coughs>,
# <yawns>, <sniffles> (wrong for an elder companion). The voice agent strips them for any other TTS model.
VOICE_TAGS = ("<laugh>", "<giggle>", "<sigh>", "<exhales>", "<whispers>", "<excited>", "<slow>", "<pauses>")

# Per-user /turn rate limit (a stuck recognizer loop must not flood core-api or the LLM).
TURN_RATE_PER_S = float(os.environ.get("TURN_RATE_PER_S", "2"))
TURN_RATE_BURST = int(os.environ.get("TURN_RATE_BURST", "6"))

# A conversation ends after this much silence; its summary then goes to the family (wellbeing.py).
CONVERSATION_IDLE_S = float(os.environ.get("CONVERSATION_IDLE_S", "180"))
