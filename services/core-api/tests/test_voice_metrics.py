import json
import time

from core_api.voice_metrics import load_voice_metrics, percentile


def test_percentiles_interpolate_and_ignore_missing_samples():
    assert percentile([10, 20, 30, 40], 0.5) == 25
    assert percentile([10, 20, 30, 40], 0.9) == 37
    assert percentile([], 0.9) is None


def test_metrics_endpoint_returns_only_numeric_aggregates(client, monkeypatch, tmp_path):
    now = time.time()
    source = tmp_path / "voice.jsonl"
    rows = [
        {"turn": 1, "t_end_of_speech": now - 4, "t_final_transcript": now - 3.8,
         "eos_to_final_ms": 200, "endpointing_ms": 500, "reasoning_to_audio_ms": 400,
         "eos_to_speaking_ms": 1100, "complete": True, "transcript": "synthetic phrase", "reply": "synthetic reply"},
        {"turn": 2, "t_end_of_speech": now - 2, "t_final_transcript": now - 1.8,
         "eos_to_final_ms": 300, "endpointing_ms": 700, "reasoning_to_audio_ms": 600,
         "eos_to_speaking_ms": 1600, "complete": True},
        {"metric_event": "barge_in", "turn": 2, "t_event": now - 1, "barge_in_stop_ms": 250},
        {"turn": 3, "t_final_transcript": now - 100000, "eos_to_final_ms": 9000},
    ]
    source.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    monkeypatch.setenv("ARJUN_VOICE_TURNLOG_PATH", str(source))

    response = client.get("/metrics/voice?hours=24")
    assert response.status_code == 200
    body = response.json()
    assert body["counts"] == {"turns": 2, "complete": 2, "barge_ins": 1}
    assert body["stages"]["stt"] == {"count": 2, "p50_ms": 250, "p90_ms": 290}
    assert body["stages"]["barge_in_stop"] == {"count": 1, "p50_ms": 250, "p90_ms": 250, "within_300_ms": 1}
    assert "transcript" not in response.text and "synthetic phrase" not in response.text


def test_metrics_loader_returns_empty_counts_for_missing_source(tmp_path):
    body = load_voice_metrics(24, tmp_path / "missing.jsonl", now=10_000)
    assert body["counts"] == {"turns": 0, "complete": 0, "barge_ins": 0}
    assert body["stages"]["stt"]["p50_ms"] is None
