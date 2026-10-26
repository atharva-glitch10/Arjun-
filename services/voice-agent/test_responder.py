"""One respond path for a spoken turn and a tapped turn, and the screen attributes (T6)."""

import asyncio

from bridge import BridgeReply
from responder import Responder
from screenstate import attributes_for, publish_screen
from turnlog import TurnLog


class Fakes:
    def __init__(self, tmp_path, replies):
        self.replies = list(replies)
        self.asked, self.said, self.published = [], [], []
        self.turns = TurnLog("mr-IN", tmp_path / "t.jsonl")
        self.r = Responder(self.turns, self.ask, self.say, self.publish, lambda: "FALLBACK LINE")

    async def ask(self, text):
        self.asked.append(text)
        return self.replies.pop(0)

    async def say(self, text):
        self.said.append(text)

    async def publish(self, reply, turn):
        self.published.append((reply.screen, turn))


def _reply(text="ठीक आहे", mode="care", ask=False, screen="reply"):
    return BridgeReply(text, mode, ask, 12.0, screen=screen, intent="X")


def _run(coro):
    return asyncio.run(coro)


def test_voice_and_tap_take_the_same_path_with_the_same_result(tmp_path):
    out = []
    for source in ("voice", "tap"):
        f = Fakes(tmp_path, [_reply("ठीक आहे, आठवण नोंदवली.", screen="saved")])
        f.turns.path = tmp_path / f"{source}.jsonl"
        if source == "voice":
            f.turns.final_transcript(1.0, "हो", "mr-IN")
        res = _run(f.r.respond("हो", source))
        out.append((res, f.asked, f.said, f.published))
    assert out[0] == out[1] == ("spoken", ["हो"], ["ठीक आहे, आठवण नोंदवली."], [("saved", 1)])


def test_tap_turn_does_not_claim_a_voice_turn_that_is_still_collecting(tmp_path):
    f = Fakes(tmp_path, [_reply()])
    f.turns.final_transcript(1.0, "उद्या सकाळी", "mr-IN")  # a spoken sentence still being collected
    _run(f.r.respond("हो", "tap"))
    assert f.turns._collecting() is not None and f.turns._collecting()["transcript"] == "उद्या सकाळी"


def test_a_stale_plain_reply_is_skipped_and_the_screen_is_left_alone(tmp_path):
    f = Fakes(tmp_path, [_reply(), _reply()])
    f.turns.final_transcript(1.0, "पहिलं", None)

    async def scenario():
        async def ask(text):
            f.turns.final_transcript(2.0, "दुसरं", None)  # the user speaks while reasoning runs
            return _reply()

        f.r.ask = ask
        return await f.r.respond("पहिलं", "voice")

    assert _run(scenario()) == "skipped"
    assert f.said == [] and f.published == []


def test_safety_and_confirmation_replies_are_spoken_even_when_stale(tmp_path):
    for reply in (_reply(mode="safety", screen="safety"), _reply(ask=True, screen="confirm")):
        f = Fakes(tmp_path, [reply])
        f.turns.final_transcript(1.0, "पहिलं", None)

        async def scenario(f=f, reply=reply):
            async def ask(text):
                f.turns.final_transcript(2.0, "दुसरं", None)
                return reply

            f.r.ask = ask
            return await f.r.respond("पहिलं", "voice")

        assert _run(scenario()) == "spoken" and f.said == [reply.text]


def test_a_publish_failure_never_silences_the_reply(tmp_path):
    f = Fakes(tmp_path, [_reply()])

    async def boom(reply, turn):
        raise RuntimeError("attributes unavailable")

    f.r.publish = boom
    assert _run(f.r.respond("आज काय आहे", "voice")) == "spoken" and f.said == ["ठीक आहे"]


def test_tts_failure_speaks_the_fixed_fallback_once(tmp_path):
    f = Fakes(tmp_path, [_reply("hello")])
    calls = []

    async def flaky(text):
        calls.append(text)
        if text == "hello":
            raise RuntimeError("tts down")

    f.r.say = flaky
    _run(f.r.respond("x", "voice"))
    assert calls == ["hello", "FALLBACK LINE"]


# ---- screen attributes ----------------------------------------------------------------------------
def test_attributes_carry_screen_turn_and_the_spoken_text():
    assert attributes_for(_reply("ठीक आहे", screen="confirm"), 3) == {
        "arjun.screen": "confirm",
        "arjun.turn": "3",
        "arjun.reply": "ठीक आहे",
        "arjun.item": "",
    }


def test_a_very_long_reply_is_cut_for_the_attribute_only():
    attrs = attributes_for(_reply("अ" * 2000), 1)
    assert len(attrs["arjun.reply"]) == 600  # attributes are for short state, not for stories


def test_safety_mode_always_wins_over_the_screen_field():
    assert attributes_for(_reply(mode="safety", screen="reply"), 4)["arjun.screen"] == "safety"
    assert attributes_for(_reply(mode="safety", screen="confirm"), 4)["arjun.screen"] == "safety"


def test_publish_screen_sets_attributes_on_the_participant():
    class P:
        got = None

        async def set_attributes(self, a):
            self.got = a

    p = P()
    _run(publish_screen(p, _reply(screen="saved"), 2))
    assert p.got == {"arjun.screen": "saved", "arjun.turn": "2", "arjun.reply": "ठीक आहे", "arjun.item": ""}
