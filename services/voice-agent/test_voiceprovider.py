"""The TESTING voice-provider switch: selection, the Sarvam plugin arguments, tag stripping, turn-log tags."""

import json

import pytest
import voiceprovider
from turnlog import TurnLog
from voice import stt_options


class FakePlugin:
    """Stands in for livekit.plugins.sarvam: records the arguments, needs no key and no network."""

    class STT:
        def __init__(self, **kw):
            self.kw = kw

    class TTS:
        def __init__(self, **kw):
            self.kw = kw


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, "gnani"), ("", "gnani"), ("gnani", "gnani"), ("sarvam", "sarvam"), (" SARVAM ", "sarvam"), ("whatever", "gnani")],
)
def test_the_provider_defaults_to_gnani_and_only_the_word_sarvam_switches(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("ARJUN_VOICE_PROVIDER", raising=False)
    else:
        monkeypatch.setenv("ARJUN_VOICE_PROVIDER", value)
    assert voiceprovider.provider() == expected


def test_sarvam_is_built_with_the_requested_marathi_models(monkeypatch):
    monkeypatch.delenv("ARJUN_SARVAM_SPEAKER", raising=False)
    stt, tts = voiceprovider.make_sarvam(FakePlugin)
    assert stt.kw == {"language": "mr-IN", "model": "saaras:v3", "mode": "transcribe"}
    assert tts.kw == {"target_language_code": "mr-IN", "model": "bulbul:v3", "speaker": "shubh"}


def test_the_speaker_can_be_overridden_and_a_blank_value_keeps_the_default(monkeypatch):
    monkeypatch.setenv("ARJUN_SARVAM_SPEAKER", "amit")
    assert voiceprovider.make_sarvam(FakePlugin)[1].kw["speaker"] == "amit"
    monkeypatch.setenv("ARJUN_SARVAM_SPEAKER", "  ")
    assert voiceprovider.make_sarvam(FakePlugin)[1].kw["speaker"] == "shubh"


def test_the_default_speaker_is_in_the_real_plugins_bulbul_v3_list():
    from livekit.plugins.sarvam.tts import MODEL_SPEAKER_COMPATIBILITY

    assert voiceprovider.DEFAULT_SPEAKER in MODEL_SPEAKER_COMPATIBILITY["bulbul:v3"]["all"]


def test_the_start_line_names_both_models():
    assert voiceprovider.start_line() == "voice provider: sarvam (stt saaras:v3, tts bulbul:v3)"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ठेवली: उद्या सकाळी १०:००, डॉक्टर.", "ठेवली: उद्या सकाळी १०:००, डॉक्टर."),
        ("[laugh] छान!", "छान!"),
        ("छान [giggle] झालं", "छान झालं"),
        ("<laugh> छान [sigh] झालं <whispers>", "छान झालं"),
        ("[slow]  नमस्कार  [pauses]", "नमस्कार"),
        ("आकडा [1] आणि [2]", "आकडा आणि"),  # short bracketed bits are treated as tags too
    ],
)
def test_timbre_tags_never_reach_bulbul(text, expected):
    assert voiceprovider.sarvam_text(text) == expected


def test_the_turn_log_rows_say_which_services_made_them(tmp_path):
    path = tmp_path / "turns.jsonl"
    log = TurnLog("mr-IN", path=path, stt_provider="sarvam", tts_provider="sarvam")
    assert log._new()["stt_provider"] == "sarvam" and log._new()["tts_provider"] == "sarvam"
    default = TurnLog("mr-IN", path=path)
    row = default._new()
    assert (row["stt_provider"], row["tts_provider"]) == ("gnani", "gnani")
    json.dumps(row)  # stays a plain JSON line


def test_stt_options_match_supported_plugin_constructor(monkeypatch):
    monkeypatch.setenv("GNANI_STT_FORMAT", "transcribe")
    monkeypatch.setenv("GNANI_STT_SAMPLE_RATE", "16000")
    monkeypatch.setenv("GNANI_STT_LANGUAGE", "mr-IN")
    assert stt_options() == {
        "language": "mr-IN", "format": "transcribe", "itn_native_numerals": True, "sample_rate": 16000
    }


@pytest.mark.parametrize("value", ["codemix", "transliterate", "nonsense"])
def test_unsupported_stt_modes_fail_fast(monkeypatch, value):
    monkeypatch.setenv("GNANI_STT_FORMAT", value)
    with pytest.raises(ValueError, match="GNANI_STT_FORMAT"):
        stt_options()


def test_auto_language_is_not_claimed_without_a_supported_adapter(monkeypatch):
    monkeypatch.setenv("GNANI_STT_LANGUAGE", "auto")
    with pytest.raises(ValueError, match="Auto-LID adapter"):
        stt_options()


def test_invalid_sample_rate_fails_fast(monkeypatch):
    monkeypatch.setenv("GNANI_STT_SAMPLE_RATE", "12345")
    with pytest.raises(ValueError, match="GNANI_STT_SAMPLE_RATE"):
        stt_options()
