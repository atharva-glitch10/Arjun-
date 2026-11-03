"""TESTING SWITCH: which speech provider the voice session uses (ARJUN_VOICE_PROVIDER, default gnani).

gnani  = Prisma (STT) + Timbre (TTS). This is the contest path and stays the default; none of its code lives here.
sarvam = Sarvam Saaras (STT) + Bulbul (TTS), for comparing recognition and voice only. It is a TESTING switch: the
         contest demo must speak through Gnani (CLAUDE.md), so never record or publish a demo with sarvam on.

Pure functions plus a factory that takes the plugin module as an argument, so the tests need no network and no key.
"""

import os
import re

from voice import strip_tags

STT_MODEL = "saaras:v3"
TTS_MODEL = "bulbul:v3"
LANGUAGE = "mr-IN"
# A male voice from the plugin's bulbul:v3 list (all of its speakers take Indian languages incl. Marathi).
DEFAULT_SPEAKER = "shubh"

_BRACKET_TAG = re.compile(r"\[[^\[\]]{1,30}\]")


def provider() -> str:
    """"gnani" (default, also for any unknown value) or "sarvam"."""
    return "sarvam" if os.environ.get("ARJUN_VOICE_PROVIDER", "gnani").strip().lower() == "sarvam" else "gnani"


def sarvam_text(text: str) -> str:
    """What goes to Bulbul: no Timbre emotion tags, neither <laugh> nor [laugh]. Bulbul would read them aloud."""
    return re.sub(r"\s{2,}", " ", _BRACKET_TAG.sub("", strip_tags(text))).strip()


def start_line() -> str:
    return f"voice provider: sarvam (stt {STT_MODEL}, tts {TTS_MODEL})"


def make_sarvam(sarvam):  # type: ignore[no-untyped-def]
    """(stt, tts) from the livekit sarvam plugin module. The key is SARVAM_API_KEY (the plugin reads it itself)."""
    stt = sarvam.STT(language=LANGUAGE, model=STT_MODEL, mode="transcribe")
    tts = sarvam.TTS(
        target_language_code=LANGUAGE,
        model=TTS_MODEL,
        speaker=os.environ.get("ARJUN_SARVAM_SPEAKER", DEFAULT_SPEAKER).strip() or DEFAULT_SPEAKER,
    )
    return stt, tts
