"""Text and voice must match (2026-11-10): one string, one language tag, for the screen, the history and the TTS. And the TTS locale / voice
choice for hi / mr / en, the fallback when a language has no voice, and the speech-recognition hints."""

import httpx
import pytest
from agent import prisma_language_hints
from bridge import BridgeReply, ask_reasoning
from screenstate import attributes_for
from voice import strip_tags, tts_plan, tts_text, tts_voice_for

LINES = {
    "hi": "ठीक है, अब मैं हिंदी में बात करूंगा।",
    "mr": "ठीक आहे, आता मी मराठी भाषेत बोलेन.",
    "en": "Okay, I will speak English now.",
}


def reply(lang, text, speech=""):
    return BridgeReply(text=text, mode="care", awaiting_confirmation=False, round_trip_ms=1.0, language=lang, speech=speech)


@pytest.mark.parametrize("lang", ["hi", "mr", "en"])
def test_the_string_sent_to_tts_is_the_string_on_the_screen_with_the_same_language_tag(lang):
    r = reply(lang, LINES[lang])
    for model in ("timbre-v2.5", "timbre-v3.0"):
        assert tts_text(r.text, r.speech, model) == r.text  # no speech variant: exactly the screen line, untranslated
    attrs = attributes_for(r, 1)
    assert attrs["arjun.reply"] == r.text and attrs["arjun.reply_lang"] == lang  # the page renders this string with this tag
    assert tts_plan(r.language, "mr-IN") == ({"hi": "hi-IN", "mr": "mr-IN", "en": "en-IN"}[lang], False)


@pytest.mark.parametrize("lang", ["hi", "mr", "en"])
def test_voice_tags_never_change_the_words(lang):
    tagged = reply(lang, LINES[lang], speech="<laugh> " + LINES[lang])
    assert tts_text(tagged.text, tagged.speech, "timbre-v3.0") == "<laugh> " + LINES[lang]
    assert strip_tags(tts_text(tagged.text, tagged.speech, "timbre-v3.0")).strip() == tagged.text  # same words as the screen
    assert tts_text(tagged.text, tagged.speech, "timbre-v2.5").strip() == tagged.text  # tags removed for a model without them


def test_the_active_switch_and_reply_language_reach_the_page():
    attrs = attributes_for(BridgeReply(text="x", mode="care", awaiting_confirmation=False, round_trip_ms=1.0, language="hi", active_language="hi"), 2)
    assert attrs["arjun.active_lang"] == "hi" and attrs["arjun.reply_lang"] == "hi"


def test_the_bridge_carries_language_and_active_language_from_reasoning():
    def handler(request):
        return httpx.Response(200, json={"reply": "ठीक है।", "mode": "care", "awaiting_confirmation": False, "language": "hi", "active_language": "hi"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    got = ask_reasoning(1, "मुझसे हिंदी में बात करना", http=http)
    assert (got.language, got.active_language) == ("hi", "hi")


# ---- voice choice and fallback ---------------------------------------------------------------------------------------
def test_each_of_hi_mr_en_has_its_own_timbre_locale_and_the_other_gnani_languages_too():
    for prefix, locale in {"hi": "hi-IN", "mr": "mr-IN", "en": "en-IN", "ta": "ta-IN", "te": "te-IN", "kn": "kn-IN", "ml": "ml-IN",
                           "bn": "bn-IN", "gu": "gu-IN", "pa": "pa-IN"}.items():
        assert tts_plan(prefix + "-IN", "mr-IN") == (locale, False)
        assert tts_plan(prefix, "mr-IN") == (locale, False)


def test_a_language_without_a_voice_is_spoken_with_the_closest_configured_one_and_flagged(caplog):
    assert tts_plan("xx-IN", "mr-IN") == ("mr-IN", True)  # agent.py logs `tts_fallback` for this
    assert tts_plan("fr", "hi-IN") == ("hi-IN", True)
    assert tts_plan(None, "mr-IN") == ("mr-IN", False) and tts_plan("", "mr-IN") == ("mr-IN", False)  # nothing to fall back FROM
    assert tts_plan("hi-en", "mr-IN") == ("hi-en", False)


def test_the_voice_for_each_language_defaults_to_the_configured_one(monkeypatch):
    monkeypatch.delenv("GNANI_TTS_MULTILINGUAL_VOICE", raising=False)
    for prefix in ("hi", "mr", "en"):
        assert tts_voice_for(prefix, tts_plan(prefix, "mr-IN")[0], "Omkar") == "Omkar"
    monkeypatch.setenv("GNANI_TTS_MULTILINGUAL_VOICE", "1")
    assert tts_voice_for("hi", "hi-IN", "Omkar") == "Esha" and tts_voice_for("en", "en-IN", "Omkar") == "Esha"
    assert tts_voice_for("mr", "mr-IN", "Omkar") == "Omkar"  # the multilingual voice is for hi / en only


# ---- speech recognition follows the switch ----------------------------------------------------------------------------
def test_recognition_hints_cover_mr_hi_en_so_a_switch_between_them_needs_no_restart(monkeypatch):
    monkeypatch.delenv("GNANI_STT_LANGUAGE_HINTS", raising=False)
    assert prisma_language_hints(["mr"]) == ["mr-IN", "hi-IN", "en-IN"]  # several hints -> Prisma auto-detects per utterance
    assert prisma_language_hints(["hi"]) == ["hi-IN", "en-IN"]
    assert prisma_language_hints(["en"]) == ["en-IN", "hi-IN"]
    assert prisma_language_hints(["ta"]) == ["ta-IN"]  # another language is pinned: a permanent switch takes effect next session
