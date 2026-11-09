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
        self.r = Responder(self.turns, self.ask, self.say, self.publish)

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
    assert calls == ["hello"]


# ---- screen attributes ----------------------------------------------------------------------------
def test_attributes_carry_screen_turn_and_the_spoken_text():
    assert attributes_for(_reply("ठीक आहे", screen="confirm"), 3) == {
        "arjun.screen": "confirm",
        "arjun.turn": "3",
        "arjun.reply": "ठीक आहे",
        "arjun.item": "",
        "arjun.thinking": "0",  # a published reply always clears the thinking marker
        "arjun.action": "",  # and the previous action (the page performs each one once)
        "arjun.speech_style": '{"rate": "normal", "volume": "normal", "simple": false}',
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
    assert p.got == {
        "arjun.screen": "saved", "arjun.turn": "2", "arjun.reply": "ठीक आहे", "arjun.item": "", "arjun.thinking": "0", "arjun.action": "",
        "arjun.speech_style": '{"rate": "normal", "volume": "normal", "simple": false}',
    }


def test_silent_reply_is_not_published_or_spoken(tmp_path):
    f = Fakes(tmp_path, [BridgeReply("", "care", False, 1.0, silent=True)])
    assert _run(f.r.respond("[video_call_stopped]")) == "silent"
    assert f.said == [] and f.published == []


# ---- two-step flow: /turn/prepare -> filler while /turn runs -> hold line at 5 s -----------------------------
class SlowFakes(Fakes):
    def __init__(self, tmp_path, delay, prep, slow_after_s=5.0):
        super().__init__(tmp_path, [_reply("उत्तर")])
        self.delay, self.events = delay, []
        self.r = Responder(self.turns, self.ask, self.say, self.publish, prepare=prep, slow_after_s=slow_after_s)

    async def ask(self, text):
        self.events.append("ask_start")
        await asyncio.sleep(self.delay)
        self.events.append("ask_done")
        return await super().ask(text)

    async def say(self, text):
        self.events.append(f"say:{text}")
        await super().say(text)


def _prep(result, delay=0.0):
    async def prepare(text):
        await asyncio.sleep(delay)
        if isinstance(result, Exception):
            raise result
        return result
    return prepare


def test_filler_is_spoken_while_the_turn_is_still_running(tmp_path):
    f = SlowFakes(tmp_path, 0.05, _prep({"needs_web": True, "filler": "बघतो…", "hold": "थोडा वेळ…"}))
    assert _run(f.r.respond("आज पाऊस पडेल का")) == "spoken"
    assert f.said == ["बघतो…", "उत्तर"]
    assert f.events.index("ask_start") < f.events.index("say:बघतो…") < f.events.index("ask_done")  # in parallel


def test_no_filler_when_prepare_says_no_fails_or_is_slow(tmp_path):
    for prep in (
        _prep({"needs_web": False, "filler": ""}),
        _prep(RuntimeError("down")),
        _prep({"needs_web": True, "filler": "बघतो…"}, delay=1.0),  # slower than the hard stop
        None,
    ):
        f = SlowFakes(tmp_path, 0.0, prep)
        assert _run(f.r.respond("आज पाऊस पडेल का")) == "spoken"
        assert f.said == ["उत्तर"]


def test_hold_line_is_spoken_once_when_the_answer_is_late(tmp_path):
    f = SlowFakes(tmp_path, 0.3, _prep({"needs_web": True, "filler": "बघतो…", "hold": "थोडा वेळ लागतोय…"}), slow_after_s=0.1)
    _run(f.r.respond("आज पाऊस पडेल का"))
    assert f.said == ["बघतो…", "थोडा वेळ लागतोय…", "उत्तर"]


def test_hold_line_also_covers_a_slow_turn_without_a_filler(tmp_path):
    f = SlowFakes(tmp_path, 0.3, _prep({"needs_web": False}), slow_after_s=0.1)
    _run(f.r.respond("नमस्कार"))
    assert f.said == ["थोडा वेळ लागतोय…", "उत्तर"]


def test_a_fast_answer_gets_no_hold_line(tmp_path):
    f = SlowFakes(tmp_path, 0.0, _prep({"needs_web": False}), slow_after_s=0.1)
    _run(f.r.respond("नमस्कार"))
    assert f.said == ["उत्तर"]


def test_defaults_match_the_budget():
    import bridge
    import responder
    assert responder.SLOW_AFTER_S == 4.0 and bridge.REASONING_TIMEOUT_S == 9.0 and bridge.PREPARE_TIMEOUT_S <= 0.3
