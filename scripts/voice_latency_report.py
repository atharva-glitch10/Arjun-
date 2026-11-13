"""Summarize voice-agent turnlog timings without exposing transcripts."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = ROOT / "eval" / "results" / "turns.jsonl"

STAGES = (
    ("eos_to_final_ms", "EOS to final (STT)"),
    ("final_to_llm_first_token_ms", "Final to first safe LLM sentence"),
    ("llm_to_first_audio_ms", "First safe sentence to first audio"),
    ("eos_to_speaking_ms", "EOS to speaking (total)"),
)
DOMINANT_STAGES = STAGES[:3]


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def load_turns(path: Path) -> list[dict[str, Any]]:
    turns = []
    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            turns.append(row)
    return turns


def _values(rows: list[dict[str, Any]], key: str) -> list[float]:
    return [value for row in rows if isinstance((value := row.get(key)), (int, float))]


def _fmt(value: float | None) -> str:
    return "—" if value is None else str(round(value))


def _table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
    print("| " + " | ".join(headers) + " |")
    print("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        print("| " + " | ".join(row) + " |")


def report(path: Path) -> None:
    turns = load_turns(path)
    print("### Voice latency by stage (milliseconds)")
    _table(
        ("Stage", "n", "p50", "p90"),
        [
            (
                label,
                str(len(_values(turns, key))),
                _fmt(percentile(_values(turns, key), 0.50)),
                _fmt(percentile(_values(turns, key), 0.90)),
            )
            for key, label in STAGES
        ],
    )

    by_language: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in turns:
        language = str(row.get("language_detected") or row.get("language_selected") or "unknown")
        by_language[language].append(row)
    print("\n### Voice latency by language (milliseconds)")
    language_rows = []
    for language in sorted(by_language):
        language_turns = by_language[language]
        for key, label in STAGES:
            values = _values(language_turns, key)
            language_rows.append(
                (language, label, str(len(values)), _fmt(percentile(values, 0.50)), _fmt(percentile(values, 0.90)))
            )
    _table(("Language", "Stage", "n", "p50", "p90"), language_rows)

    print("\n### Five slowest spoken turns")
    slowest = sorted(
        (row for row in turns if isinstance(row.get("eos_to_speaking_ms"), (int, float))),
        key=lambda row: row["eos_to_speaking_ms"],
        reverse=True,
    )[:5]
    slow_rows = []
    for row in slowest:
        stages = [(key, label, row[key]) for key, label in DOMINANT_STAGES if isinstance(row.get(key), (int, float))]
        dominant = max(stages, key=lambda stage: stage[2]) if stages else (None, "not measured", None)
        language = str(row.get("language_detected") or row.get("language_selected") or "unknown")
        slow_rows.append(
            (
                str(row.get("turn", "—")),
                language,
                str(round(row["eos_to_speaking_ms"])),
                dominant[1],
            )
        )
    _table(("Turn", "Language", "EOS to speaking ms", "Dominant stage"), slow_rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG, help=f"turnlog JSONL (default: {DEFAULT_LOG})")
    args = parser.parse_args()
    report(args.log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
