import briefing_audio as audio
from fastapi.testclient import TestClient


def test_synthesis_endpoint_requires_internal_key(monkeypatch):
    monkeypatch.setenv("CORE_API_KEY", "test-key")
    client = TestClient(audio.app)
    assert client.post("/synthesize", json={"text": "नमस्कार"}).status_code == 401


def test_synthesis_returns_ogg_using_verified_plugin_options(monkeypatch):
    monkeypatch.setenv("CORE_API_KEY", "test-key")
    monkeypatch.setattr(audio, "_selection", ("timbre-v2.5", "Omkar"))
    monkeypatch.setattr(audio, "tts_choice", lambda: {"language": "mr-IN", "method": "sse"})
    captured = {}

    class TTS:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def synthesize(self, text):
            captured["text"] = text
            return self

        async def collect(self):
            return [object()]

    monkeypatch.setattr(audio.gnani, "TTS", TTS)
    monkeypatch.setattr(audio, "_frames_to_wav", lambda frames: b"RIFFfake-wav")
    monkeypatch.setattr(audio, "_wav_to_ogg", lambda wav: b"OggSfake-opus")
    response = TestClient(audio.app).post(
        "/synthesize", json={"text": "आजचा सारांश"}, headers={"X-API-Key": "test-key"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/ogg"
    assert response.headers["x-tts-model"] == "timbre-v2.5"
    assert response.content == b"OggSfake-opus"
    assert captured["model"] == "timbre-v2.5" and captured["voice"] == "Omkar"
    assert captured["synthesize_method"] == "sse" and captured["text"] == "आजचा सारांश"


def test_wav_conversion_uses_ffmpeg_to_encode_ogg_opus(monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return type("Result", (), {"returncode": 0, "stdout": b"OggSencoded", "stderr": b""})()

    monkeypatch.setattr(audio.subprocess, "run", run)
    assert audio._wav_to_ogg(b"RIFFwav") == b"OggSencoded"
    args, kwargs = calls[0]
    assert "libopus" in args and "pipe:0" in args and "pipe:1" in args
    assert kwargs["input"] == b"RIFFwav" and "timeout" in kwargs
