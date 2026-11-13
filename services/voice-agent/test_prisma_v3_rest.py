"""REST transport for Prisma v3 (mock httpx only: no network, no real audio, no real key)."""
import asyncio
import io
import json
import wave

import httpx
import prisma_v3
import pytest
from livekit import rtc
from prisma_v3 import PrismaV3STT, clean_language_codes


def frame(seconds: float, rate: int = 16000) -> rtc.AudioFrame:
    n = int(seconds * rate)
    return rtc.AudioFrame(b"\x01\x00" * n, rate, 1, n)


def make(monkeypatch, handler, **kw):
    monkeypatch.delenv("GNANI_STT_LANGUAGE", raising=False)
    monkeypatch.delenv("GNANI_STT_LANGUAGE_HINTS", raising=False)
    monkeypatch.delenv("GNANI_STT_PREV_TEXT", raising=False)
    adapter = PrismaV3STT(api_key="unit-test-key", transport="rest", keyterms=["Medicine A"], **kw)
    rec = adapter._rest_recognizer()
    rec._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), headers={"X-API-Key-ID": "unit-test-key"})
    return adapter, rec


def fields(request: httpx.Request) -> dict:
    boundary = request.headers["content-type"].split("boundary=")[1]
    out = {}
    for part in request.content.decode("latin-1").split("--" + boundary)[1:-1]:
        head, _, value = part.partition("\r\n\r\n")
        if 'name="' in head and "filename" not in head:
            out[head.split('name="')[1].split('"')[0]] = value.rsplit("\r\n", 1)[0].encode("latin-1").decode("utf-8")
    return out


def ok(text="नमस्कार", lang="mr-IN", **extra):
    return httpx.Response(200, json={"success": True, "transcript": text, "model": "prisma-v3.0",
                                     "detected_language_code": lang, "processing_time": 0.2,
                                     "end_to_end_latency": 0.4, **extra})


def test_indic_auto_request_fields(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return ok()

    adapter, _ = make(monkeypatch, handler)
    event = asyncio.run(adapter._recognize_impl([frame(2)], language="x", conn_options=None))
    req = seen[0]
    f = fields(req)
    assert str(req.url) == "https://api.vachana.ai/stt/v3"
    assert req.headers["X-API-Key-ID"] == "unit-test-key"
    assert f["model"] == "prisma-v3.0" and f["language_code"] == "indic-auto" and f["format"] == "transcribe"
    assert "multi_lang_code" not in f and "multi_lang_codes" not in f and "previous_text" not in f
    assert "Medicine A" in json.loads(f["keyterms"]) and "Arjun" in json.loads(f["keyterms"])
    assert event.alternatives[0].text == "नमस्कार"
    assert event.alternatives[0].metadata == {"detected_language_code": "mr-IN"}
    assert not adapter.capabilities.streaming


def test_eval_wav_entry_point_uses_rest_and_enforces_clip_duration(monkeypatch):
    adapter, _ = make(monkeypatch, lambda _request: ok("नमस्कार", "mr-IN"))
    assert asyncio.run(adapter.transcribe_wav(b"wav-data", 2.0)) == ("नमस्कार", "mr-IN")
    with pytest.raises(ValueError, match="duration"):
        asyncio.run(adapter.transcribe_wav(b"wav-data", 31.0))


def test_empty_then_language_list_retry_once(monkeypatch):
    seen = []

    def handler(request):
        seen.append(fields(request)["language_code"])
        return ok("") if len(seen) == 1 else ok("औषध", "hi-IN")

    adapter, _ = make(monkeypatch, handler)
    event = asyncio.run(adapter._recognize_impl([frame(1.5)], conn_options=None))
    assert seen == ["indic-auto", "mr-IN,hi-IN,en-IN,kn-IN"]  # the list REPLACES indic-auto, never combined
    assert event.alternatives[0].text == "औषध"


def test_short_clip_empty_is_not_retried_and_tiny_clip_skipped(monkeypatch):
    seen = []
    adapter, _ = make(monkeypatch, lambda r: (seen.append(1), ok(""))[1])
    asyncio.run(adapter._recognize_impl([frame(0.5)], conn_options=None))
    assert len(seen) == 1
    asyncio.run(adapter._recognize_impl([frame(0.2)], conn_options=None))
    assert len(seen) == 1


def test_429_waits_then_retries_once(monkeypatch):
    calls, sleeps = [], []
    real_sleep = asyncio.sleep

    async def fake_sleep(s):
        sleeps.append(s)
        await real_sleep(0)

    monkeypatch.setattr(prisma_v3.asyncio, "sleep", fake_sleep)

    def handler(request):
        calls.append(1)
        return httpx.Response(429, json={"detail": {"error_code": "RATE_LIMITED"}}) if len(calls) == 1 else ok()

    adapter, _ = make(monkeypatch, handler)
    event = asyncio.run(adapter._recognize_impl([frame(2)], conn_options=None))
    assert len(calls) == 2 and sleeps == [0.4]
    assert event.alternatives[0].text == "नमस्कार"


def test_only_one_request_in_flight(monkeypatch):
    state = {"now": 0, "peak": 0}

    class Slow(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
            await asyncio.sleep(0.02)
            state["now"] -= 1
            return ok()

    adapter, rec = make(monkeypatch, lambda r: ok())
    rec._client = httpx.AsyncClient(transport=Slow())

    async def run():
        await asyncio.gather(*(adapter._recognize_impl([frame(2)], conn_options=None) for _ in range(4)))

    asyncio.run(run())
    assert state["peak"] == 1


def test_504_twice_falls_back_to_websocket_once(monkeypatch):
    calls = []
    adapter, rec = make(monkeypatch, lambda r: (calls.append(1), httpx.Response(504, json={"error": "x", "code": "UPSTREAM_TIMEOUT"}))[1])

    async def ws_once(wav):
        return "वेबसॉकेट", "hi-IN"

    monkeypatch.setattr(rec, "_ws_once", ws_once)
    event = asyncio.run(adapter._recognize_impl([frame(2)], conn_options=None))
    assert len(calls) == 2
    assert event.alternatives[0].text == "वेबसॉकेट"


def test_400_is_not_retried_and_gives_empty_transcript(monkeypatch):
    calls = []
    body = {"success": False, "error": {"type": "INVALID_LANGUAGE_CODE", "message": "bad"}}
    adapter, rec = make(monkeypatch, lambda r: (calls.append(1), httpx.Response(400, json=body))[1])

    async def boom(wav):
        raise AssertionError("no websocket fallback for 4xx")

    monkeypatch.setattr(rec, "_ws_once", boom)
    event = asyncio.run(adapter._recognize_impl([frame(2)], conn_options=None))
    assert len(calls) == 1 and event.alternatives[0].text == ""


def test_invalid_language_codes_are_dropped_and_capped(monkeypatch):
    assert clean_language_codes("mr-IN,hi-in,xx-IN,en-IN") == ["mr-IN", "en-IN"]
    assert clean_language_codes("mr-IN,hi-IN,en-IN,kn-IN,ta-IN") == ["mr-IN", "hi-IN", "en-IN", "kn-IN"]
    monkeypatch.setenv("GNANI_STT_LANGUAGE", "mr-IN")
    assert prisma_v3.rest_language_code() == "indic-auto"


def test_long_audio_is_split_into_wavs_of_at_most_30_seconds(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request.content)
        return ok("एक")

    adapter, _ = make(monkeypatch, handler)
    event = asyncio.run(adapter._recognize_impl([frame(61)], conn_options=None))
    assert len(seen) == 3
    assert event.alternatives[0].text == "एक एक एक"
    for clip, seconds in prisma_v3.RestRecognizer._clips([frame(61)]):
        with wave.open(io.BytesIO(clip)) as w:
            assert w.getnframes() / w.getframerate() <= 30 and w.getnchannels() == 1
        assert seconds <= 30.0


def test_previous_text_only_when_enabled(monkeypatch):
    seen = []
    adapter, _ = make(monkeypatch, lambda r: (seen.append(fields(r)), ok("एक दोन"))[1])
    monkeypatch.setenv("GNANI_STT_PREV_TEXT", "1")
    asyncio.run(adapter._recognize_impl([frame(2)], conn_options=None))
    asyncio.run(adapter._recognize_impl([frame(2)], conn_options=None))
    assert "previous_text" not in seen[0] and seen[1]["previous_text"] == "एक दोन"


def test_ws_remains_default(monkeypatch):
    monkeypatch.delenv("GNANI_STT_TRANSPORT", raising=False)
    adapter = PrismaV3STT(api_key="unit-test-key")
    assert adapter.transport == "ws" and adapter.capabilities.streaming
    with pytest.raises(NotImplementedError):
        asyncio.run(adapter._recognize_impl([frame(1)], conn_options=None))
