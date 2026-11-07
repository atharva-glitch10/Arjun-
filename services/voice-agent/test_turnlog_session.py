"""Turn log, task E (2026-10-31): one JSON line per turn with the transcript, reply, intent, mode, source, endpointing,
reasoning, TTS-first-audio and end-of-speech -> speaking times, the session id, and WHY a turn has no speaking time.
Evidence (logs/voice-agent.app.log, 22:47): a "33 s" turn was a 42 s monologue whose FIRST pause had been kept as the end of
speech; rows with a reply but no speaking time were replies that never played (she spoke again, or Timbre answered 429)."""

import json

import pytest
from turnlog import TurnLog


def rows(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def make(tmp_path, **kw):
    return TurnLog("mr-IN", tmp_path / "t.jsonl", **kw)


# ---- the 33 s turn was a measurement error ---------------------------------------------------------------------
def test_a_long_monologue_measures_from_the_last_end_of_speech(tmp_path):
    log = make(tmp_path)
    log.end_of_speech(11.0)  # a pause inside the story
    log.final_transcript(11.3, "अथर्वनी आज चिकन बनवलं होतं", "mr-IN")
    log.end_of_speech(42.2)  # she finally stops
    log.final_transcript(42.5, "आणि मी चपाती आणि भात", "mr-IN")
    idx = log.reasoning_started("x", t=42.7)
    log.reasoning_done(idx, 42.8, "ठीक", "companion", 100)
    log.speaking_for(idx)
    log.agent_speaking(44.0)
    (t,) = rows(tmp_path / "t.jsonl")
    assert t["transcript"] == "अथर्वनी आज चिकन बनवलं होतं आणि मी चपाती आणि भात"
    assert t["t_end_of_speech"] == 42.2
    assert t["eos_to_audio_ms"] == t["eos_to_speaking_ms"] == 1800  # not 33 s
    assert t["endpointing_ms"] == 200  # last final -> reasoning, not first final -> reasoning


def test_end_of_speech_arriving_after_the_last_final_also_wins(tmp_path):
    log = make(tmp_path)
    log.final_transcript(5.0, "एक", None)
    log.end_of_speech(4.9)
    log.final_transcript(9.0, "दोन", None)
    log.end_of_speech(9.1)  # the final came first this time
    idx = log.reasoning_started("x", t=9.3)
    log.speaking_for(idx)
    log.agent_speaking(10.0)
    assert rows(tmp_path / "t.jsonl")[0]["t_end_of_speech"] == 9.1


# ---- one complete line per turn ---------------------------------------------------------------------------------
def test_a_spoken_turn_has_every_field_the_brief_asks_for(tmp_path):
    log = make(tmp_path, session="AJ_test")
    log.end_of_speech(100.0)
    log.final_transcript(100.4, "आज काय आहे", "mr-IN")
    idx = log.reasoning_started("आज काय आहे", t=100.5)
    log.reasoning_done(idx, 100.6, "आज काही नाही", "care", 90, intent="LIST_TODAY", source="rules")
    log.speaking_for(idx, t=100.7)
    log.agent_speaking(101.2)
    (t,) = rows(tmp_path / "t.jsonl")
    assert t["transcript"] == "आज काय आहे" and t["reply"] == "आज काही नाही"
    assert (t["intent"], t["mode"], t["source"], t["session"]) == ("LIST_TODAY", "care", "rules", "AJ_test")
    assert (t["endpointing_ms"], t["reasoning_ms"], t["tts_first_audio_ms"], t["eos_to_speaking_ms"]) == (100, 90, 500, 1200)
    assert t["outcome"] == "spoken" and t["complete"] is True


def test_barge_in_logs_vad_start_to_agent_stop_in_milliseconds_without_text(tmp_path):
    log = make(tmp_path, session="synthetic-session")
    log.final_transcript(10.0, "synthetic", "mr-IN")
    idx = log.reasoning_started("synthetic", t=10.1)
    log.reasoning_done(idx, 10.2, "synthetic reply", "care", 100)
    log.speaking_for(idx, t=10.21)
    log.agent_speaking(10.3)
    log.user_started_speaking(10.5)
    log.agent_stopped_speaking(10.75)
    rows_ = rows(tmp_path / "t.jsonl")
    (event,) = [row for row in rows_ if row.get("metric_event") == "barge_in"]
    assert event["barge_in_stop_ms"] == 250
    assert "transcript" not in event and "reply" not in event


def test_a_line_never_contains_a_secret_or_audio(tmp_path):
    log = make(tmp_path, session="AJ_test")
    log.final_transcript(1.0, "हो", None)
    idx = log.reasoning_started("हो", t=1.1)
    log.reasoning_done(idx, 1.2, "ठीक", "care", 5, intent="CONFIRM_YES", source="rules")
    log.speaking_for(idx)
    log.agent_speaking(1.5)
    text = (tmp_path / "t.jsonl").read_text(encoding="utf-8").lower()
    for banned in ("api_key", "secret", "bearer", "token"):
        assert banned not in text


# ---- why a turn has no speaking time ----------------------------------------------------------------------------
def test_a_reply_that_did_not_play_says_why(tmp_path):
    log = make(tmp_path)
    log.final_transcript(1.0, "डंड", None)
    idx = log.reasoning_started("डंड", t=1.1)
    log.reasoning_done(idx, 1.5, "मला नीट समजलं नाही", "care", 400)
    log.speaking_for(idx)
    log.not_spoken(idx, "interrupted")  # she started talking again
    (t,) = rows(tmp_path / "t.jsonl")
    assert t["outcome"] == "interrupted" and t["complete"] is False and "t_agent_speaking" not in t


def test_a_tts_failure_is_recorded_as_such(tmp_path):
    log = make(tmp_path)
    log.final_transcript(1.0, "हो", None)
    idx = log.reasoning_started("हो", t=1.1)
    log.reasoning_done(idx, 1.2, "ठीक", "care", 10)
    log.not_spoken(idx, "tts_failed")
    assert rows(tmp_path / "t.jsonl")[0]["outcome"] == "tts_failed"


def test_turns_left_open_when_the_session_closes_are_named(tmp_path):
    log = make(tmp_path)
    log.final_transcript(1.0, "एक", None)  # never taken by reasoning
    idx = log.reasoning_started("दोन", t=2.0)  # a different, taken turn
    log.final_transcript(3.0, "तीन", None)
    log.reasoning_done(idx, 2.5, "reply", "care")  # replied, never spoken
    log.close()
    outcomes = {r["transcript"]: r["outcome"] for r in rows(tmp_path / "t.jsonl")}
    assert set(outcomes.values()) <= {"no_reply", "not_spoken", "session_closed"}
    assert "no_reply" in outcomes.values() and "not_spoken" in outcomes.values()


def test_stale_and_skipped_keep_their_reason(tmp_path):
    log = make(tmp_path)
    log.final_transcript(1.0, "एक", None)
    idx = log.reasoning_started("एक", t=1.1)
    log.skip(idx, "stale")
    assert rows(tmp_path / "t.jsonl")[0]["outcome"] == "stale"


# ---- reconnects ---------------------------------------------------------------------------------------------------
def test_the_counter_never_goes_backwards_inside_a_session(tmp_path):
    log = make(tmp_path, start=1000)
    seen = []
    for i in range(5):
        log.final_transcript(float(i * 10), f"t{i}", None)
        idx = log.reasoning_started(f"t{i}", t=i * 10 + 0.5)
        seen.append(idx)
        log.bump()  # deliveries and closes also take numbers
        log.speaking_for(idx)
        log.agent_speaking(i * 10 + 1.0)
    assert seen == sorted(seen) and len(set(seen)) == 5 and seen[0] > 1000


def test_a_reconnect_starts_above_the_previous_session(tmp_path):
    first = make(tmp_path, start=TurnLog.base_for(1_793_467_000.0), session="A")
    for _ in range(30):
        first.bump()
    second = make(tmp_path, start=TurnLog.base_for(1_793_467_060.0), session="B")  # a minute later
    assert second.index > first.index


def test_the_base_is_time_derived_and_small_enough_for_a_screen_attribute():
    assert TurnLog.base_for(1_793_467_000.0) < 10**9
    assert TurnLog.base_for(1_793_467_001.0) > TurnLog.base_for(1_793_467_000.0)
    assert TurnLog.base_for(0.0) == 0


@pytest.mark.parametrize("outcome", ["spoken", "interrupted", "tts_failed", "stale", "no_reply", "not_spoken"])
def test_the_outcome_names_are_stable(outcome):
    assert outcome in TurnLog.OUTCOMES


# ---- the responder fills the line in --------------------------------------------------------------------------
def _responder(tmp_path, say, reply=None):
    import asyncio

    from bridge import BridgeReply
    from responder import Responder

    log = make(tmp_path, session="AJ_r")
    replies = [reply or BridgeReply("ठीक", "care", False, 12.0, intent="LIST_TODAY", source="rules")]

    async def ask(text):
        return replies.pop(0)

    async def publish(r, turn):
        return None

    r = Responder(log, ask, say, publish, lambda: "FALLBACK")
    return log, lambda text: asyncio.run(r.respond(text, "tap"))


def test_the_responder_records_intent_and_source(tmp_path):
    async def say(text):
        return True

    log, go = _responder(tmp_path, say)
    go("आज काय आहे")
    log.agent_speaking(9e9)  # playout started
    (t,) = rows(tmp_path / "t.jsonl")
    assert (t["intent"], t["source"], t["session"]) == ("LIST_TODAY", "rules", "AJ_r")


def test_a_say_that_was_interrupted_is_written_at_once_as_interrupted(tmp_path):
    async def say(text):
        return False  # LiveKit: the speech handle was interrupted before it played

    log, go = _responder(tmp_path, say)
    assert go("आज काय आहे") == "spoken"
    (t,) = rows(tmp_path / "t.jsonl")
    assert t["outcome"] == "interrupted"


def test_a_tts_exception_is_recorded_and_the_fallback_line_is_still_tried(tmp_path):
    said = []

    async def say(text):
        said.append(text)
        if len(said) == 1:
            raise RuntimeError("Gnani TTS SSE Error (429)")
        return True

    log, go = _responder(tmp_path, say)
    go("आज काय आहे")
    assert said[-1] == "FALLBACK"
    assert rows(tmp_path / "t.jsonl")[0]["outcome"] == "tts_failed"
