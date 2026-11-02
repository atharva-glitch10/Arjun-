"""Media mode (voice-controlled apps): while a video plays, the mic also hears the video. Only the wake word, a bare
control phrase or a SAFETY phrase gets through; everything else is ignored; safety is never ignored."""

import asyncio
import json

import httpx
import pytest
from bridge import BridgeReply, ask_reasoning, media_gate
from mediamode import MediaMode, starts_with_wake_word
from screenstate import ACTION, action_json, attributes_for, delivery_attributes
from turnlog import TurnLog


def run(coro):
    return asyncio.run(coro)


class Gate:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    async def __call__(self, text):
        self.calls.append(text)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


_DEFAULT = {"safety": False, "control": False}


def mode(answer=_DEFAULT, playing=True):
    m = MediaMode(Gate(answer))
    m.playing = playing
    return m


@pytest.mark.parametrize("text", ["अर्जुन, थांबव", "अर्जुन थांबव", "Arjun stop", "अर्जून बंद कर", "arjun, volume down"])
def test_the_wake_word_is_recognised(text):
    assert starts_with_wake_word(text)


@pytest.mark.parametrize("text", ["थांबव अर्जुन", "आज मी बागेत गेले", "", "अर्जुनाने धनुष्य उचलले"])
def test_other_words_are_not_the_wake_word(text):
    assert not starts_with_wake_word(text)


def test_nothing_is_filtered_when_nothing_plays():
    m = mode(playing=False)
    assert run(m.decide("काहीही")) == ("pass", "not_playing") and m.gate.calls == []


def test_the_videos_own_audio_is_ignored():
    m = mode()
    assert run(m.decide("जय जय रघुवीर समर्थ")) == ("ignore", "ignored_media")


def test_the_wake_word_passes_without_asking_the_gate():
    m = mode()
    assert run(m.decide("अर्जुन, आवाज कमी कर")) == ("pass", "wake_word") and m.gate.calls == []


def test_a_bare_control_phrase_passes():
    assert run(mode({"safety": False, "control": True}).decide("थांबव")) == ("pass", "control")


def test_a_safety_phrase_is_never_ignored():
    assert run(mode({"safety": True, "control": False}).decide("छातीत दुखतंय")) == ("pass", "safety")


@pytest.mark.parametrize("failure", [None, RuntimeError("boom"), httpx.ConnectError("down")])
def test_when_the_gate_cannot_answer_the_transcript_is_passed_on_not_ignored(failure):
    m = mode(failure)
    verdict, reason = run(m.decide("छातीत दुखतंय"))
    assert verdict == "pass" and reason == "gate_unavailable"


def test_state_follows_the_actions_and_the_page():
    m = mode(playing=False)
    m.on_action({"type": "open", "kind": "youtube_video", "value": "x", "title": "t"})
    assert m.playing
    m.on_action({"type": "control", "kind": "volume_down"})
    assert m.playing  # a volume change does not end the video
    m.on_action({"type": "control", "kind": "stop"})
    assert not m.playing
    m.on_page_state("playing")
    assert m.playing
    m.on_page_state("stopped")  # the video ended by itself
    assert not m.playing
    m.on_action({"type": "open", "kind": "whatsapp", "value": "https://wa.me/1"})
    assert not m.playing  # a chat window has no video audio
    m.on_page_state("playing")
    m.reset()  # the page left the room
    assert not m.playing


# ---- the gate call and the attribute --------------------------------------------------------------------------
def test_media_gate_returns_the_answer_or_none_when_reasoning_is_down():
    ok = httpx.Client(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json={"safety": True, "control": False})))
    assert media_gate(1, "छातीत दुखतंय", ok) == {"safety": True, "control": False}

    def down(req):
        raise httpx.ConnectError("x", request=req)

    assert media_gate(1, "x", httpx.Client(transport=httpx.MockTransport(down))) is None


def test_bridge_carries_the_action_from_reasoning():
    action = {"type": "open", "kind": "youtube_video", "value": "AAAAAAAAAAA", "title": "भजन"}
    body = {"reply": "भजन लावतो.", "mode": "care", "awaiting_confirmation": False, "action": action}
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body)))
    assert ask_reasoning(1, "भजन लावा", client).action == action
    body.pop("action")
    assert ask_reasoning(1, "x", client).action is None


def test_the_action_is_published_as_json_with_the_turn_number():
    reply = BridgeReply("भजन लावतो.", "care", False, 1.0,
                        action={"type": "open", "kind": "youtube_video", "value": "AAAAAAAAAAA", "title": "भजन"})
    attrs = attributes_for(reply, 7)
    assert json.loads(attrs[ACTION]) == {"type": "open", "kind": "youtube_video", "value": "AAAAAAAAAAA",
                                         "title": "भजन", "turn": 7}


def test_no_action_clears_the_attribute_and_a_safety_reply_never_carries_one():
    plain = BridgeReply("ठीक आहे", "care", False, 1.0)
    assert attributes_for(plain, 3)[ACTION] == ""
    none = BridgeReply("ठीक आहे", "care", False, 1.0, action={"type": "none", "kind": "", "value": "", "title": ""})
    assert action_json(none, 3) == ""
    safety = BridgeReply("112", "safety", False, 1.0, action={"type": "open", "kind": "link", "value": "https://x.io"})
    assert action_json(safety, 4) == ""
    # a delivered reminder leaves the last action alone (the page performs each action once, by its turn number)
    assert ACTION not in delivery_attributes({"screen": "reminder", "text": "आठवण", "item": "reminder:1"}, 5)


def test_an_ignored_transcript_is_logged_without_its_words(tmp_path):
    log = TurnLog("mr-IN", tmp_path / "t.jsonl")
    log.final_transcript(10.0, "जय जय रघुवीर समर्थ", "mr-IN")
    log.ignore_collected("ignored_media")
    (row,) = [json.loads(x) for x in (tmp_path / "t.jsonl").read_text(encoding="utf-8").splitlines()]
    assert row["outcome"] == "ignored_media" and row["transcript"] == ""
    # the next real sentence starts a fresh turn
    log.final_transcript(20.0, "अर्जुन थांबव", "mr-IN")
    assert log.reasoning_started("अर्जुन थांबव") == row["turn"] + 1
