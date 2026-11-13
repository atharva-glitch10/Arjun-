"""Voice settings and the text that goes to Timbre. Pure where it matters, so it is tested.

- Prisma (STT): format="transcribe" turns on inverse text normalisation ("दहा वाजता" -> "10 वाजता"), and
  itn_native_numerals renders those digits in Devanagari ("१० वाजता"). Reasoning reads both digit forms.
- Timbre (TTS): timbre-v3.0 understands inline voice tags such as <laugh> / <slow>. Reasoning sends them in
  `speech` (chosen at runtime by the LLM); for any other model they are stripped so they are never read aloud.
- SSE: synthesis over one pooled HTTP connection per sentence (no new WebSocket per reply, ~1 s saved per reply
  on the dev laptop when measured with the WebSocket path on 2026-10-26).
"""

import os
import re

STT_FORMATS = frozenset({"verbatim", "transcribe"})
STT_SAMPLE_RATES = frozenset({8000, 16000, 44100, 48000})
STT_LANGUAGES = frozenset({"mr-IN", "hi-IN", "en-IN", "auto"})
TTS_LANGUAGE_MAP = {"mr": "mr-IN", "hi": "hi-IN", "en": "en-IN", "bn": "bn-IN", "gu": "gu-IN",
                   "kn": "kn-IN", "ml": "ml-IN", "pa": "pa-IN", "ta": "ta-IN", "te": "te-IN", "or": "or-IN"}

TAG_MODELS = frozenset({"timbre-v3.0"})
_TAG = re.compile(r"<\s*[a-z][a-z ]{1,20}\s*>", re.IGNORECASE)


def env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None or v.strip() == "" else v.strip().lower() in ("1", "true", "yes", "on")


def strip_tags(text: str) -> str:
    return re.sub(r"\s{2,}", " ", _TAG.sub("", text)).strip()


def tts_text(reply: str, speech: str, model: str) -> str:
    """What to send to Timbre: the tagged line for a tag-capable model, the plain line otherwise."""
    if model in TAG_MODELS and speech.strip():
        return speech.strip()
    return strip_tags(speech) if speech.strip() else reply


def slower_text(text: str) -> str:
    """Add light spoken pauses when no verified Timbre speed control is available."""
    return re.sub(r"([,;])\s*", r"\1 … ", text.strip())


def stt_options() -> dict[str, object]:
    """Options supported by the pinned LiveKit Gnani plugin (not Prisma v3-only options)."""
    fmt = os.environ.get("GNANI_STT_FORMAT", "transcribe").strip().lower()
    if fmt not in STT_FORMATS:
        raise ValueError("GNANI_STT_FORMAT must be verbatim or transcribe for the installed Gnani plugin")
    try:
        sample_rate = int(os.environ.get("GNANI_STT_SAMPLE_RATE", "16000"))
    except ValueError as exc:
        raise ValueError("GNANI_STT_SAMPLE_RATE must be an integer") from exc
    if sample_rate not in STT_SAMPLE_RATES:
        raise ValueError("GNANI_STT_SAMPLE_RATE must be 8000, 16000, 44100, or 48000")
    language = os.environ.get("GNANI_STT_LANGUAGE", "mr-IN").strip()
    if language not in STT_LANGUAGES:
        raise ValueError("GNANI_STT_LANGUAGE must be mr-IN, hi-IN, en-IN, or auto")
    if language == "auto":
        # The installed plugin requires a language code. Do not pretend its language hint is Auto-LID.
        raise ValueError("GNANI_STT_LANGUAGE=auto requires a Prisma v3 Auto-LID adapter, which is not installed")
    return {
        "language": language,
        "format": fmt,
        "itn_native_numerals": env_bool("GNANI_ITN_NATIVE_NUMERALS", True),
        "sample_rate": sample_rate,
    }


def tts_choice() -> dict[str, str]:
    """Primary Timbre settings and the known-good fallback (v2.5 + Omkar was verified live on 2026-10-21)."""
    return {
        "model": os.environ.get("GNANI_TTS_MODEL", "timbre-v3.0"),
        "voice": os.environ.get("GNANI_TTS_VOICE", "Avinash"),
        "language": os.environ.get("GNANI_TTS_LANGUAGE", "").strip(),  # empty = none: every reply names its own language
        "method": os.environ.get("GNANI_TTS_METHOD", "sse"),
        "fallback_model": os.environ.get("GNANI_TTS_FALLBACK_MODEL", "timbre-v2.5"),
        "fallback_voice": os.environ.get("GNANI_TTS_FALLBACK_VOICE", "Omkar"),
    }


def tts_language_for(detected: str | None, fallback: str = "") -> str:
    """Map a language code ("hi", "hi-IN") to its Timbre locale. Unknown / absent -> `fallback` (callers pass none)."""
    normalized = (detected or "").replace("_", "-").lower()
    if normalized == "hi-en":
        return "hi-en"
    prefix = normalized.split("-", 1)[0]
    return TTS_LANGUAGE_MAP.get(prefix, fallback)


def tts_plan(detected: str | None, fallback: str) -> tuple[str, bool]:
    """(Timbre locale, fell_back). `fell_back` is True when the reply language has no Timbre locale of its own and the closest
    configured one speaks it instead: the text is still shown, and the caller logs `tts_fallback`."""
    prefix = (detected or "").replace("_", "-").split("-", 1)[0].lower()
    if prefix == "hi-en" or (detected or "").lower() == "hi-en":
        return "hi-en", False
    if not prefix:
        return fallback, False
    if prefix in TTS_LANGUAGE_MAP:
        return TTS_LANGUAGE_MAP[prefix], False
    return fallback, True


def tts_voice_for(detected: str | None, language: str, configured: str, model: str = "") -> str:
    """Choose from documented Timbre v3 catalogue where known; preserve configured v2.5 language voice otherwise.
    "Esha" is NOT in timbre-v3.0's catalogue (live 400 on 2026-11-10: every English / Hindi reply was silent), so it is only
    used when the model in force is not a v3 one."""
    prefix = (detected or "").replace("_", "-").split("-", 1)[0].lower()
    if prefix in {"en", "hi"} or language == "hi-en":
        if os.environ.get("GNANI_TTS_MULTILINGUAL_VOICE", "0") == "1" and "v3" not in model.lower():
            return "Esha"
    return configured
