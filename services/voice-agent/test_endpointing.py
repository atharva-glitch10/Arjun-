"""Mode-aware endpointing (task D). Elderly speakers pause mid-sentence: care turns end after 0.8 s of silence,
companion / story turns wait at least 1.6 s (up to 4.0 s), and a sentence that ends in "आणि / पण / म्हणजे / की" is held
for more speech instead of being answered half-said. Timings here are fakes: nothing sleeps."""

import asyncio

import pytest
from bridge import BridgeReply
from endpointing import (
    ConjunctionHold,
    EndpointingPolicy,
    ends_with_conjunction,
    settings_from_env,
    turn_handling_options,
)
from responder import Responder
from turnlog import TurnLog


def run(coro):
    return asyncio.run(coro)


# ---- the numbers ------------------------------------------------------------------------------------------------
def test_defaults_are_care_08_and_companion_16_to_40():
    p = EndpointingPolicy()
    assert p.options() == {"min_delay": 0.8, "max_delay": 2.5}  # a session starts in care timing
    p.set_mode("companion")
    assert p.options() == {"min_delay": 1.6, "max_delay": 4.0}
    p.set_mode("care")
    assert p.options() == {"min_delay": 0.8, "max_delay": 2.5}


def test_barge_in_vad_threshold_is_100ms_and_keeps_false_interruption_recovery():
    options = turn_handling_options({"ARJUN_TURN_DETECTION": "vad"})
    assert options["interruption"] == {
        "enabled": True, "mode": "vad", "min_duration": 0.1, "min_words": 0,
        "resume_false_interruption": True, "false_interruption_timeout": 2.0,
    }
    assert options["turn_detection"] == "vad"


@pytest.mark.parametrize("mode", ["safety", "fallback", "", "anything-else"])
def test_every_other_mode_uses_the_quick_care_timing(mode):
    p = EndpointingPolicy()
    p.set_mode("companion")
    p.set_mode(mode)
    assert p.options()["min_delay"] == 0.8


def test_env_overrides_every_number():
    s = settings_from_env({
        "ARJUN_MIN_ENDPOINTING_S": "0.5", "ARJUN_CARE_MAX_ENDPOINTING_S": "2",
        "ARJUN_COMPANION_MIN_ENDPOINTING_S": "2.2", "ARJUN_MAX_ENDPOINTING_S": "5",
    })
    assert (s.care_min, s.care_max, s.companion_min, s.companion_max) == (0.5, 2.0, 2.2, 5.0)


def test_nonsense_env_values_fall_back_and_max_is_never_below_min():
    s = settings_from_env({"ARJUN_MIN_ENDPOINTING_S": "fast", "ARJUN_COMPANION_MIN_ENDPOINTING_S": "6",
                           "ARJUN_MAX_ENDPOINTING_S": "4"})
    assert s.care_min == 0.8
    assert s.companion_min == 6.0 and s.companion_max >= s.companion_min


# ---- conjunctions ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "काय सांगू तुला डोकं दुखतं आहे माझं थोडं आणि", "मी बागेत गेले होते आणि,", "मला जायचं होतं पण.",
    "म्हणजे", "तो आला की", "ani", "mi gele hote ani", "मैं गया और", "आणि  ",
])
def test_a_trailing_conjunction_is_detected(text):
    assert ends_with_conjunction(text)


@pytest.mark.parametrize("text", [
    "", "   ", "आणि मग मी घरी आले", "मी पाणी प्यायले", "उद्या दहा वाजता", "पणती लावली", "कीर्तन ऐकलं", "हो",
])
def test_a_finished_sentence_is_not_held(text):
    assert not ends_with_conjunction(text)


# ---- the hold --------------------------------------------------------------------------------------------------
class FakeSpeech:
    """wait_for_speech(timeout): says whether she started talking again within `timeout`. Never sleeps."""

    def __init__(self, resumes: bool):
        self.resumes, self.asked = resumes, []

    async def __call__(self, timeout: float) -> bool:
        self.asked.append(timeout)
        return self.resumes


def test_a_complete_sentence_is_answered_at_once_without_waiting():
    speech = FakeSpeech(True)
    hold = ConjunctionHold(EndpointingPolicy(), speech)
    assert run(hold.settle("उद्या दहा वाजता डॉक्टर")) == "उद्या दहा वाजता डॉक्टर"
    assert speech.asked == []


def test_a_cut_off_sentence_waits_up_to_the_rest_of_the_max_delay():
    speech = FakeSpeech(False)  # she does not speak again
    policy = EndpointingPolicy()
    policy.set_mode("companion")
    hold = ConjunctionHold(policy, speech)
    assert run(hold.settle("डोकं दुखतं आहे माझं थोडं आणि")) == "डोकं दुखतं आहे माझं थोडं आणि"
    assert speech.asked == [pytest.approx(4.0 - 1.6)]  # the silence already waited (min) counts toward the max


def test_care_timing_holds_for_max_minus_min_too():
    speech = FakeSpeech(False)
    run(ConjunctionHold(EndpointingPolicy(), speech).settle("चहा घेतला आणि"))
    assert speech.asked == [pytest.approx(2.5 - 0.8)]


def test_when_she_goes_on_the_first_part_is_kept_and_joined_to_the_next():
    speech = FakeSpeech(True)
    hold = ConjunctionHold(EndpointingPolicy(), speech)
    assert run(hold.settle("मी बागेत गेले होते आणि")) is None  # not answered yet
    assert hold.held == "मी बागेत गेले होते आणि"
    assert run(hold.settle("तिथे फुलं पाहिली")) == "मी बागेत गेले होते आणि तिथे फुलं पाहिली"
    assert hold.held == ""


def test_a_held_part_is_not_lost_when_the_next_turn_is_empty_noise():
    speech = FakeSpeech(True)
    hold = ConjunctionHold(EndpointingPolicy(), speech)
    run(hold.settle("मी बागेत गेले होते आणि"))
    assert run(hold.settle("  ")) == "मी बागेत गेले होते आणि"


def test_two_cut_offs_in_a_row_keep_growing_until_a_sentence_ends_or_she_stops():
    speech = FakeSpeech(True)
    hold = ConjunctionHold(EndpointingPolicy(), speech)
    assert run(hold.settle("मी गेले आणि")) is None
    assert run(hold.settle("तिथे पण")) is None
    assert run(hold.settle("फुलं पाहिली")) == "मी गेले आणि तिथे पण फुलं पाहिली"


def test_a_tap_or_text_is_never_held():
    speech = FakeSpeech(True)
    assert run(ConjunctionHold(EndpointingPolicy(), speech).settle("आणि", allow_hold=False)) == "आणि"
    assert speech.asked == []


# ---- the reply's mode drives the next turn's delay ---------------------------------------------------------------
def test_the_responder_tells_the_policy_the_mode_of_the_reply(tmp_path):
    modes = []
    replies = [BridgeReply("छान", "companion", False, 5.0, intent="CHAT"), BridgeReply("ठेवली", "care", False, 5.0)]

    async def ask(text):
        return replies.pop(0)

    async def say(text):
        return None

    async def publish(reply, turn):
        return None

    r = Responder(TurnLog("mr-IN", tmp_path / "t.jsonl"), ask, say, publish, lambda: "F", on_mode=modes.append)
    run(r.respond("a", "tap"))
    run(r.respond("b", "tap"))
    assert modes == ["companion", "care"]


# ---- turn detection (task E): VAD-based by default ---------------------------------------------------------------
@pytest.mark.parametrize("value, expected", [
    (None, "vad"), ("", "vad"), ("vad", "vad"), ("VAD", "vad"), ("stt", "stt"), ("auto", None), ("cloud", None),
    ("nonsense", "vad"),
])
def test_turn_detection_defaults_to_vad_and_auto_restores_the_cloud_detector(value, expected):
    from endpointing import turn_detection_from_env

    env = {} if value is None else {"ARJUN_TURN_DETECTION": value}
    assert turn_detection_from_env(env) == expected
