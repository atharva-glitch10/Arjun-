"""Timbre v3 voice tags, Prisma transcribe + native numerals, the thinking marker, hands-free (no idle close)."""

import asyncio

import httpx
import pytest
from bridge import BridgeReply, ask_reasoning
from idle import IdleCloser, IdlePolicy
from responder import Responder
from turnlog import TurnLog
from voice import slower_text, strip_tags, stt_options, tts_choice, tts_text


def test_tags_go_to_timbre_v3_only():
    assert tts_text("वा, छान!", "<laugh> वा, छान!", "timbre-v3.0") == "<laugh> वा, छान!"
    assert tts_text("वा, छान!", "<laugh> वा, छान!", "timbre-v2.5") == "वा, छान!"
    assert tts_text("ठीक आहे.", "", "timbre-v3.0") == "ठीक आहे."
    assert strip_tags("<slow> हळू <pauses> बोला") == "हळू बोला"


def test_slow_style_adds_pauses_without_unverified_tts_parameters():
    assert slower_text("पहिले वाचा, मग सांगा.") == "पहिले वाचा, … मग सांगा."


def test_defaults_follow_the_brief(monkeypatch):
    for k in ("GNANI_STT_FORMAT", "GNANI_ITN_NATIVE_NUMERALS", "GNANI_TTS_MODEL", "GNANI_TTS_METHOD"):
        monkeypatch.delenv(k, raising=False)
    assert stt_options() == {
        "language": "mr-IN", "format": "transcribe", "itn_native_numerals": True, "sample_rate": 16000
    }
    t = tts_choice()
    assert t["model"] == "timbre-v3.0" and t["method"] == "sse"
    assert (t["fallback_model"], t["fallback_voice"]) == ("timbre-v2.5", "Omkar")  # the voice verified live
    monkeypatch.setenv("GNANI_STT_FORMAT", "nonsense")
    monkeypatch.setenv("GNANI_ITN_NATIVE_NUMERALS", "0")
    with pytest.raises(ValueError, match="GNANI_STT_FORMAT"):
        stt_options()


def test_bridge_reads_the_spoken_line_with_tags():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"reply": "वा!", "speech": "<laugh> वा!", "mode": "companion",
                                         "awaiting_confirmation": False, "screen": "story", "intent": "CHAT"})

    r = ask_reasoning(1, "मी आज गाणं गायलं", http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert (r.text, r.speech) == ("वा!", "<laugh> वा!")


def test_thinking_marker_is_on_while_reasoning_works_and_off_after(tmp_path):
    marks, said = [], []
    order = []

    async def ask(text):
        order.append(("ask", marks[-1]))
        return BridgeReply("वा!", "companion", False, 10.0, screen="story", speech="<laugh> वा!")

    async def say(text):
        said.append(text)

    async def publish(reply, turn):
        pass

    async def thinking(on):
        marks.append(on)

    r = Responder(TurnLog("mr-IN", tmp_path / "t.jsonl"), ask, say, publish, lambda: "F", thinking=thinking,
                  speakable=lambda rep: tts_text(rep.text, rep.speech, "timbre-v3.0"))
    asyncio.run(r.respond("मी आज गाणं गायलं"))
    assert order == [("ask", True)] and marks == [True, False]
    assert said == ["<laugh> वा!"]


def test_hands_free_never_closes_the_session():
    async def get_busy():
        return {"pending": False, "safety_hold": False, "queued": 0}

    async def never():
        raise AssertionError("must not be called")

    closer = IdleCloser(IdlePolicy(0), quiet=lambda: True, get_busy=get_busy, say_closing=never,
                        publish_closed=never, shutdown=never, poll_s=0.01)
    assert asyncio.run(closer.tick()) is False
    asyncio.run(asyncio.wait_for(closer.run(), 1))  # returns at once instead of looping
    assert IdlePolicy(0).may_close(True, {"queued": 0}) is False
