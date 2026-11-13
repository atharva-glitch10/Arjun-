import json

from turnlog import TurnLog


def _rows(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def _say(log, text, reply, t_reply, t_audio):
    idx = log.reasoning_started(text)
    log.reasoning_done(idx, t_reply, reply, "care")
    log.speaking_for(idx)
    log.agent_speaking(t_audio)
    return idx


def test_full_turn_writes_one_line_with_latencies(tmp_path):
    log = TurnLog("mr-IN", tmp_path / "t.jsonl")
    log.end_of_speech(100.0)
    log.final_transcript(100.4, "आज काय आहे", "mr-IN")
    _say(log, "आज काय आहे", "आज काही नाही", 100.6, 101.0)
    (t,) = _rows(tmp_path / "t.jsonl")
    assert t["transcript"] == "आज काय आहे" and t["language_selected"] == "mr-IN" and t["language_detected"] == "mr-IN"
    assert (t["eos_to_final_ms"], t["final_to_reasoning_ms"], t["reasoning_to_audio_ms"], t["eos_to_audio_ms"]) == (400, 200, 400, 1000)
    assert t["complete"] is True


def test_speech_without_a_user_turn_is_not_logged(tmp_path):
    log = TurnLog("mr-IN", tmp_path / "t.jsonl")
    log.agent_speaking(5.0)
    assert not (tmp_path / "t.jsonl").exists()


def test_queued_turns_keep_their_own_transcript_reply_and_audio(tmp_path):
    """Live 2026-10-24: a second utterance arrived before the first reply, and the old log paired
    every reply with the wrong transcript. Each turn must keep its own fields."""
    log = TurnLog("mr-IN", tmp_path / "t.jsonl")
    log.end_of_speech(0.0)
    log.final_transcript(2.4, "हॅलो", "mr-IN")
    a = log.reasoning_started("हॅलो")
    log.end_of_speech(6.0)
    log.final_transcript(6.5, "आज काय आहे", "mr-IN")
    log.reasoning_done(a, 9.0, "reply A", "care")
    log.speaking_for(a)
    log.agent_speaking(11.5)
    b = log.reasoning_started("आज काय आहे")
    log.reasoning_done(b, 12.0, "reply B", "care")
    log.speaking_for(b)
    log.agent_speaking(14.8)
    rows = _rows(tmp_path / "t.jsonl")
    assert [(r["transcript"], r["reply"]) for r in rows] == [("हॅलो", "reply A"), ("आज काय आहे", "reply B")]
    assert [r["t_agent_speaking"] for r in rows] == [11.5, 14.8]
    assert [r["t_end_of_speech"] for r in rows] == [0.0, 6.0]
    assert [r["final_to_reasoning_ms"] for r in rows] == [6600, 5500]


def test_several_finals_before_the_turn_is_taken_become_one_transcript(tmp_path):
    log = TurnLog("mr-IN", tmp_path / "t.jsonl")
    log.final_transcript(1.0, "उद्या सकाळी", None)
    log.final_transcript(2.0, "दहा वाजता", None)
    _say(log, "उद्या सकाळी दहा वाजता", "r", 3.0, 4.0)
    (row,) = _rows(tmp_path / "t.jsonl")
    assert row["transcript"] == "उद्या सकाळी दहा वाजता" and row["t_final_transcript"] == 1.0


def test_final_before_end_of_speech_still_gets_its_eos(tmp_path):
    log = TurnLog("mr-IN", tmp_path / "t.jsonl")
    log.final_transcript(10.0, "हो", None)
    log.end_of_speech(10.1)
    _say(log, "हो", "ठीक", 10.5, 11.0)
    (row,) = _rows(tmp_path / "t.jsonl")
    assert row["t_end_of_speech"] == 10.1


def test_is_stale_only_when_a_newer_transcript_exists(tmp_path):
    log = TurnLog("mr-IN", tmp_path / "t.jsonl")
    log.final_transcript(1.0, "पहिलं", None)
    a = log.reasoning_started("पहिलं")
    assert not log.is_stale(a)
    log.end_of_speech(2.0)  # VAD noise alone is not a new sentence
    assert not log.is_stale(a)
    log.final_transcript(3.0, "दुसरं", None)
    assert log.is_stale(a)


def test_skipped_stale_turn_is_logged_without_audio(tmp_path):
    log = TurnLog("mr-IN", tmp_path / "t.jsonl")
    log.final_transcript(1.0, "पहिलं", None)
    a = log.reasoning_started("पहिलं")
    log.reasoning_done(a, 2.0, "old reply", "care")
    log.skip(a, "stale")
    (row,) = _rows(tmp_path / "t.jsonl")
    assert row["skipped"] == "stale" and row["complete"] is False and "t_agent_speaking" not in row


def test_close_flushes_unanswered_turns_as_incomplete(tmp_path):
    log = TurnLog("mr-IN", tmp_path / "t.jsonl")
    log.end_of_speech(1.0)
    log.final_transcript(1.2, "हो", None)
    log.close()
    (row,) = _rows(tmp_path / "t.jsonl")
    assert row["complete"] is False and "eos_to_audio_ms" not in row
    assert row["eos_to_final_ms"] == 200
    assert all(row[key] is None for key in (
        "final_to_llm_first_token_ms", "llm_to_first_audio_ms", "eos_to_speaking_ms",
    ))


def test_timing_splits_endpointing_from_reasoning_from_audio(tmp_path):
    log = TurnLog("mr-IN", tmp_path / "t.jsonl")
    log.end_of_speech(10.0)
    log.final_transcript(10.7, "हो", "mr-IN")
    idx = log.reasoning_started("हो", t=12.9)  # the end-of-turn decision came 2.2 s after the final
    log.reasoning_done(idx, 13.3, "ठीक", "care", reasoning_ms=310.4)
    log.speaking_for(idx)
    log.agent_speaking(14.4)
    (row,) = _rows(tmp_path / "t.jsonl")
    assert row["endpointing_ms"] == 2200  # final transcript -> reasoning call started
    assert row["reasoning_ms"] == 310  # the /turn round trip itself
    assert row["reasoning_to_audio_ms"] == 1100  # TTS + playout


def test_streamed_sentence_and_tts_prewarm_timings(tmp_path):
    log = TurnLog("mr-IN", tmp_path / "t.jsonl")
    log.end_of_speech(10.0)
    log.final_transcript(10.4, "काही सांगा", "mr-IN")
    idx = log.reasoning_started("काही सांगा", t=10.5)
    log.llm_first_token(idx, 11.0)  # first complete, already-guarded stream sentence
    log.reasoning_done(idx, 11.2, "ठीक आहे", "companion")
    log.speaking_for(idx, 11.2)
    log.set_tts_prewarm("hit", idx)
    log.agent_speaking(11.6)
    (row,) = _rows(tmp_path / "t.jsonl")
    assert row["final_to_llm_first_token_ms"] == 600
    assert row["llm_to_first_audio_ms"] == 600
    assert row["eos_to_speaking_ms"] == 1600
    assert row["tts_prewarm"] == "hit"


def test_tts_prewarm_default_is_recorded_per_turn(tmp_path):
    log = TurnLog("mr-IN", tmp_path / "t.jsonl")
    log.set_tts_prewarm("hit")
    idx = log.reasoning_started("नमस्कार", t=1.0, source="tap")
    log.not_spoken(idx, "no_reply")
    (row,) = _rows(tmp_path / "t.jsonl")
    assert row["tts_prewarm"] == "hit"


def test_a_tapped_turn_gets_its_own_row_and_is_marked(tmp_path):
    log = TurnLog("mr-IN", tmp_path / "t.jsonl")
    log.final_transcript(1.0, "उद्या सकाळी", None)  # a spoken sentence still being collected
    tap = log.reasoning_started("हो", t=2.0, source="tap")
    log.reasoning_done(tap, 2.3, "ठीक", "care", reasoning_ms=250)
    log.speaking_for(tap)
    log.agent_speaking(3.0)
    (row,) = _rows(tmp_path / "t.jsonl")
    assert row["source"] == "tap" and row["transcript"] == "हो" and "t_end_of_speech" not in row
    assert row["complete"] is True  # it got audio; the tap itself is its start
    assert log._collecting()["transcript"] == "उद्या सकाळी"  # untouched
