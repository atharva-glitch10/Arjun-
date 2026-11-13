"""Push-to-record clips (mock STT: no network, synthetic silence only)."""
import asyncio
import io
import wave

import clip
import pytest
from livekit.agents import LanguageCode, stt


def wav(seconds: float, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x01\x00" * int(seconds * rate))
    return buf.getvalue()


class FakeSTT:
    def __init__(self, text="नमस्कार", lang="mr-IN", error=""):
        self.text, self.lang, self.last_error, self.calls = text, lang, error, []

    async def recognize(self, frames):
        self.calls.append(frames)
        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[stt.SpeechData(language=LanguageCode("mr"), text=self.text,
                                         metadata={"detected_language_code": self.lang})])


def run(data, fake):
    return asyncio.run(clip.process_clip(data, fake))


def test_send_returns_transcript_and_language():
    fake = FakeSTT()
    res = run(wav(2), fake)
    assert (res.status, res.text, res.lang) == ("heard", "नमस्कार", "mr-IN")
    assert len(fake.calls) == 1


def test_too_short_never_reaches_stt():
    fake = FakeSTT()
    assert run(wav(0.2), fake).status == "too_short"
    assert run(b"", fake).status == "too_short"
    assert fake.calls == []


def test_30_second_clip_is_one_request():
    fake = FakeSTT()
    res = run(wav(30), fake)
    assert res.status == "heard" and len(fake.calls) == 1
    frame = fake.calls[0][0]
    assert frame.samples_per_channel / frame.sample_rate <= clip.MAX_S


def test_clip_over_30_seconds_never_reaches_stt():
    fake = FakeSTT()
    res = run(wav(31), fake)
    assert res.status == "error"
    assert fake.calls == []


def test_empty_transcript_is_a_friendly_line_not_an_error():
    res = run(wav(2), FakeSTT(text=""))
    assert res.status == "empty"
    assert "ऐकू" in clip.empty_line("mr-IN") and "catch" in clip.empty_line("en") and "सुनाई" in clip.empty_line("hi-IN")
    assert clip.empty_line("ta-IN") == clip.EMPTY_LINE["mr"]


def test_stt_failure_is_an_error_so_the_screen_offers_retry():
    assert run(wav(2), FakeSTT(text="", error="http_500")).status == "error"


def test_garbage_bytes_are_an_error():
    assert run(b"x" * 500, FakeSTT()).status == "error"


@pytest.mark.parametrize("seconds", [0.3, 1.0])
def test_boundary_length_is_sent(seconds):
    assert run(wav(seconds), FakeSTT()).status == "heard"
