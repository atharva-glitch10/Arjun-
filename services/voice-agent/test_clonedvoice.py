from types import SimpleNamespace as R

import clonedvoice as cv

VOICE = {"voice_id": 3, "name": "Rahul", "embedding": "E", "shape": [1, 768], "dtype": "torch.bfloat16"}


def reply(**kw):
    base = dict(mode="companion", screen="reply", intent="chat", action={"type": "none"}, awaiting_confirmation=False)
    return R(**(base | kw))


def test_companion_chat_may_use_cloned_voice():
    assert cv.allowed(reply())
    assert cv.allowed(reply(intent="story", screen="story", mode="story"))


def test_urgent_or_actionable_replies_never_do():
    assert not cv.allowed(reply(mode="safety"))
    assert not cv.allowed(reply(mode="fallback"))
    assert not cv.allowed(reply(intent="emergency"))
    assert not cv.allowed(reply(intent="medicine_taken"))
    assert not cv.allowed(reply(intent="reminder_add"))
    assert not cv.allowed(reply(screen="confirm"))
    assert not cv.allowed(reply(awaiting_confirmation=True))
    assert not cv.allowed(reply(action={"type": "open", "kind": "youtube_query"}))
    assert not cv.allowed(reply(intent="unknown", mode="care"))


def test_payload_swaps_preset_voice_for_embedding():
    base = {"text": "नमस्कार", "voice": "Avinash", "model": "timbre-v2.5", "language": "mr-IN",
            "audio_config": {"sample_rate": 24000}}
    voice = cv.ClonedVoice(3, "Rahul", "E", [1, 768], "torch.bfloat16")
    p = cv.cloned_payload(base, voice)
    assert p["model"] == "vachana-vc-v1" and "voice" not in p and "language" not in p
    assert p["speaker_embedding"] == {"embedding": "E", "shape": [1, 768], "dtype": "torch.bfloat16"}
    assert p["audio_config"] == {"sample_rate": 24000} and p["text"] == "नमस्कार"


def test_source_caches_and_survives_errors():
    t = [0.0]
    calls = []

    def fetch(uid):
        calls.append(uid)
        if len(calls) == 2:
            raise RuntimeError("core-api down")
        return VOICE

    src = cv.VoiceSource(7, fetch, clock=lambda: t[0])
    assert src.get().name == "Rahul" and src.get().name == "Rahul" and calls == [7]
    t[0] = 61
    assert src.get() is None  # error -> speak as Arjun
    t[0] = 122
    assert src.get().voice_id == 3
    src.forget()
    assert src.get() is None
