import json

from turnlog import TurnLog


def test_full_turn_writes_one_line_with_latencies(tmp_path):
    log = TurnLog("mr-IN", tmp_path / "t.jsonl")
    log.end_of_speech(100.0)
    log.final_transcript(100.4, "आज काय आहे", "mr-IN")
    log.reasoning_done(100.6, "आज काही नाही", "care")
    log.agent_speaking(101.0)
    lines = (tmp_path / "t.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    t = json.loads(lines[0])
    assert t["transcript"] == "आज काय आहे" and t["language_selected"] == "mr-IN" and t["language_detected"] == "mr-IN"
    assert (t["eos_to_final_ms"], t["final_to_reasoning_ms"], t["reasoning_to_audio_ms"], t["eos_to_audio_ms"]) == (400, 200, 400, 1000)
    assert t["complete"] is True


def test_speech_without_a_user_turn_is_not_logged(tmp_path):
    log = TurnLog("mr-IN", tmp_path / "t.jsonl")
    log.agent_speaking(5.0)
    assert not (tmp_path / "t.jsonl").exists()


def test_turn_without_audio_is_flushed_incomplete_on_next_turn(tmp_path):
    log = TurnLog("mr-IN", tmp_path / "t.jsonl")
    log.end_of_speech(1.0)
    log.final_transcript(1.2, "हो", None)
    log.end_of_speech(9.0)
    first = json.loads((tmp_path / "t.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert first["complete"] is False and "eos_to_audio_ms" not in first
