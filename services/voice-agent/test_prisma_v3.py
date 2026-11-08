import asyncio
import json

import httpx
import prisma_v3
import websockets
from livekit.agents import DEFAULT_API_CONNECT_OPTIONS, stt
from prisma_v3 import PrismaV3STT, user_context_terms

_HTTPX_CLIENT = httpx.Client


def test_context_fetch_only_uses_bias_fields(monkeypatch):
    def route(request):
        if request.url.path.endswith("/contacts"):
            return httpx.Response(200, json=[{"name": "Family One", "phone": "do-not-use"}] * 5)
        if request.url.path.endswith("/medicines"):
            return httpx.Response(200, json=[{"name": "Medicine A", "dose": "do-not-use"}])
        if request.url.path.endswith("/app-links"):
            return httpx.Response(200, json=[{"label": "Music", "spoken_names": ["songs"], "value": "https://private.invalid"}])
        return httpx.Response(200, json={"interests": ["Bhajan"]})

    monkeypatch.setenv("CORE_API_URL", "https://core.invalid")
    monkeypatch.setattr(prisma_v3.httpx, "Client", lambda **kw: _MockContextClient(route))
    terms, speakers = user_context_terms(7)
    assert terms == ["Bhajan", "Family One", "Medicine A", "Music", "songs"]
    assert speakers == ["Family One"]
    assert len(terms) <= 200 and len(speakers) <= 4


class _MockContextClient:
    def __init__(self, route):
        self.client = _HTTPX_CLIENT(transport=httpx.MockTransport(route), base_url="https://core.invalid")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.client.close()

    def get(self, *args, **kwargs):
        return self.client.get(*args, **kwargs)


def test_stream_uses_documented_headers_and_carries_detected_language(monkeypatch):
    captured = {}

    class FakeSocket:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def recv(self):
            return json.dumps({"type": "connected"})

        def __aiter__(self):
            async def messages():
                yield json.dumps({"type": "transcript", "text": "வணக்கம்", "detected_language_code": "ta-IN", "segment_id": "s1"})
            return messages()

        async def send(self, _data):
            return None

    def connect(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeSocket()

    monkeypatch.setattr(websockets, "connect", connect)
    adapter = PrismaV3STT(api_key="unit-test-key", sample_rate=8000, keyterms=["one"], speaker_names=["family"])
    async def run():
        stream = adapter.stream(conn_options=DEFAULT_API_CONNECT_OPTIONS)
        stream._input_ch.close()
        await stream._run()
        return await stream.__anext__()

    event = asyncio.run(run())
    assert captured["url"] == "wss://api.vachana.ai/stt/v3/stream"
    headers = captured["additional_headers"]
    assert headers["model"] == "prisma-v3.0"
    assert headers["language_code"] == "indic-auto"
    assert headers["format"] == "codemix"
    assert headers["x-sample-rate"] == "8000"
    assert json.loads(headers["keyterms"]) == ["one"]
    assert json.loads(headers["speaker_names"]) == ["family"]
    assert event.type == stt.SpeechEventType.FINAL_TRANSCRIPT
    assert str(event.alternatives[0].language) == "ta-IN"
    assert event.alternatives[0].metadata == {"detected_language_code": "ta-IN"}


def test_preferred_languages_are_sent_as_locale_hints(monkeypatch):
    captured = {}

    class Socket:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def recv(self): return '{"type":"connected"}'
        async def send(self, _data): return None
        def __aiter__(self):
            async def messages():
                if False:
                    yield ""
            return messages()

    def connect(_url, **kwargs):
        captured.update(kwargs)
        return Socket()

    monkeypatch.setattr(websockets, "connect", connect)
    async def run():
        adapter = PrismaV3STT(api_key="unit-test-key", language_hints=["ta-IN", "en-IN"])
        await adapter.stream()._run()

    asyncio.run(run())
    assert captured["additional_headers"]["language_code"] == "ta-IN,en-IN"


def test_old_plugin_compatibility_no_extra_prisma_headers():
    assert "previous_context" not in PrismaV3STT(api_key="test").__dict__


def test_context_values_are_bounded_and_deduplicated():
    adapter = PrismaV3STT(api_key="unit-test-key", keyterms=["x"] * 202, speaker_names=["a", "b", "c", "d", "e"])
    assert len(adapter.keyterms) == 1
    assert len(adapter.speaker_names) == 4


def _capture_headers(monkeypatch, first_message='{"type":"connected"}', **adapter_kw):
    captured = {}

    class Socket:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def recv(self): return first_message
        async def send(self, _data): return None
        def __aiter__(self):
            async def messages():
                if False:
                    yield ""
            return messages()

    def connect(_url, **kwargs):
        captured.update(kwargs)
        return Socket()

    monkeypatch.setattr(websockets, "connect", connect)

    async def run():
        await PrismaV3STT(api_key="unit-test-key", **adapter_kw).stream()._run()

    return captured, run


def test_devanagari_terms_are_ascii_escaped_in_headers(monkeypatch):
    """Gnani: non-ASCII keyterms JSON must be escaped in headers (raw Devanagari failed the handshake, 2026-11-08)."""
    captured, run = _capture_headers(monkeypatch, keyterms=["शुगरची गोळी", "Glimepiride"], speaker_names=["राहुल"])
    asyncio.run(run())
    headers = captured["additional_headers"]
    for value in headers.values():
        value.encode("ascii")  # raises if any header is not plain ASCII
    assert json.loads(headers["keyterms"]) == ["शुगरची गोळी", "Glimepiride"]
    assert json.loads(headers["speaker_names"]) == ["राहुल"]


def test_refused_handshake_reports_gnanis_reason(monkeypatch):
    import pytest
    from livekit.agents import APIConnectionError

    _, run = _capture_headers(monkeypatch, first_message='{"type":"error","message":"invalid language_code"}')
    with pytest.raises(APIConnectionError, match="invalid language_code"):
        asyncio.run(run())
