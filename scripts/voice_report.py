"""Print numeric-only p50/p90 voice timing metrics from eval/results/turns.jsonl."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "core-api"))

from core_api.voice_metrics import load_voice_metrics  # noqa: E402

LABELS = {
    "stt": "EOS to final (STT)",
    "final_to_reasoning": "Final to reasoning",
    "reasoning_to_first_audio": "Reasoning to first audio",
    "eos_to_speaking": "EOS to speaking",
    "barge_in_stop": "Barge-in stop",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24)
    args = parser.parse_args()
    metrics = load_voice_metrics(args.hours)
    print(f"Voice timings, last {metrics['hours']} h | turns {metrics['counts']['turns']} | complete {metrics['counts']['complete']} | barge-ins {metrics['counts']['barge_ins']}")
    print(f"{'Stage':30} {'n':>6} {'p50 ms':>10} {'p90 ms':>10}")
    for key, label in LABELS.items():
        row = metrics["stages"][key]
        p50 = "—" if row["p50_ms"] is None else str(row["p50_ms"])
        p90 = "—" if row["p90_ms"] is None else str(row["p90_ms"])
        print(f"{label:30} {row['count']:6d} {p50:>10} {p90:>10}")
    if metrics["stages"]["barge_in_stop"]["count"]:
        within = metrics["stages"]["barge_in_stop"]["within_300_ms"]
        print(f"Barge-ins at or under 300 ms: {within}/{metrics['counts']['barge_ins']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
