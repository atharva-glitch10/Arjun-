"""Runtime config. Temperatures are FIXED constants - never changed at runtime."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

EXTRACTION_TEMPERATURE = 0.0  # care mode / intent extraction / distress: always 0
# UNVERIFIED: Gnani's model-card recommendation. Must be chosen by our own testing before launch.
COMPANION_TEMPERATURE = 0.6
COMPANION_TOP_P = 0.95


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
    max_tokens: int = 120
    history_exchanges: int = 4  # last four user/assistant exchanges only

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
    else:
        base, key = get("EVON_BASE_URL"), get("EVON_API_KEY")
        model = get("EVON_MODEL") or ("gnani/gnani-evon-v3.3-30B-A3B" if base else "")
        provider = get("LLM_PROVIDER_NAME") or ("evon" if base else "none")
    template = get("LLM_SEND_TEMPLATE_KWARGS") or get("EVON_SEND_TEMPLATE_KWARGS") or "1"
    return LlmSettings(
        base_url=base,
        model=model,
        api_key=key,
        provider=provider,
        send_template_kwargs=template != "0",
        timeout_s=float(number("LLM_TIMEOUT_S", 4.0, float)),
        max_tokens=int(number("LLM_MAX_TOKENS", 120, int)),
        history_exchanges=int(number("LLM_HISTORY_EXCHANGES", 4, int)),
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
