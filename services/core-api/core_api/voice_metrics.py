"""Numeric-only summaries from voice-agent turn records; never return transcript or reply fields."""

import json
import math
import os
import time
from pathlib import Path
from typing import Any, Iterable

STAGES = {
    "stt": "eos_to_final_ms",
    "final_to_reasoning": "endpointing_ms",
    "reasoning_to_first_audio": "reasoning_to_audio_ms",
    "eos_to_speaking": "eos_to_speaking_ms",
    "barge_in_stop": "barge_in_stop_ms",
}


def turnlog_path(env: dict[str, str] | None = None) -> Path:
    values = os.environ if env is None else env
    configured = (values.get("ARJUN_VOICE_TURNLOG_PATH") or "").strip()
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else Path(__file__).resolve().parents[3] / path
    return Path(__file__).resolve().parents[3] / "eval" / "results" / "turns.jsonl"


def percentile(values: Iterable[int | float], p: float) -> int | None:
    ordered = sorted(float(v) for v in values if math.isfinite(float(v)) and v >= 0)
    if not ordered:
        return None
    pos = (len(ordered) - 1) * min(1.0, max(0.0, p))
    low, high = math.floor(pos), math.ceil(pos)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (pos - low))


def summarize(rows: Iterable[dict[str, Any]], hours: int, now: float | None = None) -> dict[str, Any]:
    current = time.time() if now is None else now
    since = current - hours * 3600
    turns: list[dict[str, Any]] = []
    barges: list[int] = []
    for row in rows:
        if row.get("metric_event") == "barge_in":
            event_at = row.get("t_event")
            if isinstance(event_at, (int, float)) and since <= event_at <= current:
                duration = row.get("barge_in_stop_ms")
                if isinstance(duration, (int, float)) and duration >= 0:
                    barges.append(int(duration))
            continue
        event_at = row.get("t_end_of_speech") or row.get("t_final_transcript")
        if isinstance(event_at, (int, float)) and since <= event_at <= current:
            turns.append(row)

    stages: dict[str, dict[str, int | None]] = {}
    for stage, field in STAGES.items():
        values = barges if stage == "barge_in_stop" else [
            row[field] for row in turns if isinstance(row.get(field), (int, float)) and row[field] >= 0
        ]
        stages[stage] = {
            "count": len(values),
            "p50_ms": percentile(values, 0.50),
            "p90_ms": percentile(values, 0.90),
        }
        if stage == "barge_in_stop":
            stages[stage]["within_300_ms"] = sum(value <= 300 for value in values)
    return {
        "hours": hours,
        "counts": {"turns": len(turns), "complete": sum(bool(row.get("complete")) for row in turns), "barge_ins": len(barges)},
        "stages": stages,
    }


def load_voice_metrics(hours: int, path: Path | None = None, now: float | None = None) -> dict[str, Any]:
    source = path or turnlog_path()
    rows: list[dict[str, Any]] = []
    try:
        with source.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue  # the voice agent may be appending this line concurrently
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        pass
    return summarize(rows, hours, now)
