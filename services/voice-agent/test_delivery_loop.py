"""T8 step 3: the voice session pulls queued deliveries and speaks them. "spoken" is reported only after playback
really completed; an interruption or a TTS failure puts the item back and never reports it as spoken."""

import asyncio

from delivery import DeliveryLoop
from sessionstate import SessionState

ITEM = {"delivery_id": 7, "kind": "reminder", "text": "आठवण: tea.", "screen": "reminder", "item": "reminder:3",
        "awaiting_confirmation": False, "language": "mr"}


class Fakes:
    def __init__(self, items=None, speak_result=True, speak_error=None, can=True, spoken_errors=0):
        self.items = list(items if items is not None else [ITEM])
        self.speak_result, self.speak_error, self.can = speak_result, speak_error, can
        self.spoken_errors = spoken_errors
        self.log: list[tuple] = []
        self.loop = DeliveryLoop(
            claim_next=self.claim_next, spoken=self.spoken, release=self.release, speak=self.speak,
            publish=self.publish, can_speak=lambda: self.can, poll_s=0, retry_sleep=self.no_sleep,
        )

    async def no_sleep(self, _):
        return None

    async def claim_next(self):
        self.log.append(("claim",))
        return self.items.pop(0) if self.items else None

    async def spoken(self, did):
        self.log.append(("spoken", did))
        if self.spoken_errors:
            self.spoken_errors -= 1
            raise RuntimeError("network")

    async def release(self, did, reason):
        self.log.append(("release", did, reason))

    async def speak(self, text):
        self.log.append(("speak", text))
        if self.speak_error:
            raise self.speak_error
        return self.speak_result

    async def publish(self, item):
        self.log.append(("publish", item["screen"], item["item"]))

    def names(self):
        return [e[0] for e in self.log]


def run(coro):
    return asyncio.run(coro)


def test_happy_path_publishes_then_speaks_then_reports_spoken_in_that_order():
    f = Fakes()
    assert run(f.loop.tick()) == "spoken"
    assert f.names() == ["claim", "publish", "speak", "spoken"]
    assert ("publish", "reminder", "reminder:3") in f.log and ("speak", "आठवण: tea.") in f.log


def test_spoken_is_not_reported_when_the_speech_was_interrupted():
    f = Fakes(speak_result=False)
    assert run(f.loop.tick()) == "interrupted"
    assert "spoken" not in f.names() and ("release", 7, "interrupted") in f.log


def test_a_tts_failure_is_released_as_a_failure_and_never_reported_spoken():
    f = Fakes(speak_error=RuntimeError("tts down"))
    assert run(f.loop.tick()) == "failed"
    assert "spoken" not in f.names() and ("release", 7, "tts") in f.log


def test_nothing_is_claimed_while_the_session_is_busy_talking():
    f = Fakes(can=False)
    assert run(f.loop.tick()) == "skipped" and f.log == []


def test_nothing_waiting_is_just_idle():
    f = Fakes(items=[])
    assert run(f.loop.tick()) == "idle" and f.names() == ["claim"]


def test_a_failing_screen_update_does_not_silence_the_item():
    f = Fakes()

    async def boom(item):
        raise RuntimeError("attributes unavailable")

    f.loop.publish = boom
    assert run(f.loop.tick()) == "spoken" and "speak" in f.names()


def test_a_failing_spoken_call_is_retried_and_the_loop_survives():
    f = Fakes(spoken_errors=2)
    assert run(f.loop.tick()) == "spoken"
    assert f.names().count("spoken") == 3  # two failures, then success


def test_a_spoken_call_that_never_works_is_given_up_without_crashing():
    f = Fakes(spoken_errors=99)
    assert run(f.loop.tick()) == "spoken_unreported"  # core-api will recycle the claim; no crash


def test_a_claim_error_does_not_kill_the_loop():
    f = Fakes()

    async def down():
        raise RuntimeError("reasoning down")

    f.loop.claim_next = down
    assert run(f.loop.tick()) == "idle"


def test_run_delivers_every_item_in_order_and_stops_when_cancelled():
    a = {**ITEM, "delivery_id": 1, "text": "one"}
    b = {**ITEM, "delivery_id": 2, "text": "two"}
    f = Fakes(items=[a, b])

    async def scenario():
        task = asyncio.create_task(f.loop.run())
        for _ in range(50):
            await asyncio.sleep(0)
            if ("spoken", 2) in f.log:
                break
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    run(scenario())
    assert [e for e in f.log if e[0] == "speak"] == [("speak", "one"), ("speak", "two")]


def test_two_sessions_sharing_one_queue_speak_an_item_exactly_once():
    """core-api's claim is atomic; each loop only speaks what its own claim returned."""
    queue = [dict(ITEM)]
    spoken_by = []

    def make(name):
        async def claim():
            return queue.pop(0) if queue else None  # the first claimer takes it

        async def speak(text):
            spoken_by.append(name)
            return True

        async def noop(*a):
            return None

        return DeliveryLoop(claim_next=claim, spoken=noop, release=noop, speak=speak, publish=noop,
                            can_speak=lambda: True, poll_s=0)

    a, b = make("A"), make("B")

    async def both():
        await asyncio.gather(a.tick(), b.tick())

    run(both())
    assert spoken_by == ["A"]


# ---- when the session counts as quiet --------------------------------------------------------------------------
def test_quiet_means_listening_nobody_speaking_no_turn_in_flight_and_no_other_speech():
    s = SessionState()
    s.on_agent_state("listening")
    assert s.quiet(False)
    assert not s.quiet(True)  # something else holds the speech lock
    s.on_user_state("speaking")
    assert not s.quiet(False)
    s.on_user_state("listening")
    s.on_agent_state("speaking")
    assert not s.quiet(False)
    s.on_agent_state("listening")
    assert s.quiet(False)


def test_a_turn_in_flight_makes_the_session_not_quiet():
    s = SessionState()
    s.on_agent_state("listening")

    async def scenario():
        async with s.turn():
            assert not s.quiet(False)
        assert s.quiet(False)

    run(scenario())


def test_the_speaking_counter_proves_audio_really_started():
    s = SessionState()
    before = s.speaking_count
    s.on_agent_state("thinking")
    assert s.speaking_count == before
    s.on_agent_state("speaking")
    assert s.speaking_count == before + 1
