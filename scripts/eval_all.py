"""Generate a safe, numbers-only system evaluation report (no transcripts or Prisma WER)."""

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "reasoning"))
sys.path.insert(0, str(ROOT / "services" / "core-api"))

from core_api.voice_metrics import load_voice_metrics  # noqa: E402
from reasoning_svc.distress import is_distress, is_emergency  # noqa: E402
from reasoning_svc.parser import Profile, parse  # noqa: E402
from reasoning_svc.readings import parse_bp  # noqa: E402

NOW = datetime(2026, 10, 6, 9, 0)
LATIN = re.compile(r"[A-Za-z]")
DEVANAGARI = re.compile(r"[\u0900-\u097f]")
DIALOGUE_FILE = ROOT / "eval" / "results" / "dialogues_final1.json"


def predict(text: str) -> tuple[str, str | None, str | None, bool]:
    if is_distress(text):
        return "DISTRESS", None, None, False
    parsed = parse(text, Profile(), NOW, "mr", has_pending=False)
    draft = parsed.draft
    if parsed.intent == "CREATE_REMINDER" and draft.missing() == "ampm":
        return parsed.intent, draft.date, None, True
    return parsed.intent, draft.date, draft.time, False


def score_cases() -> dict[str, int]:
    cases = [json.loads(line) for line in (ROOT / "eval" / "cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    intent_ok = slot_ok = slot_count = mixed_ok = mixed_count = 0
    for case in cases:
        intent, date, time_, ambiguous = predict(case["text"])
        intent_ok += intent == case["intent"]
        if "date_offset" in case:
            slot_count += 1
            expected_date = (NOW.date() + timedelta(days=case["date_offset"])).isoformat()
            slot_ok += date == expected_date and time_ == case.get("time") and ambiguous == case.get("time_ambiguous", False)
        text = case["text"]
        if LATIN.search(text) and DEVANAGARI.search(text):
            mixed_count += 1
            mixed_ok += intent == case["intent"]
    return {"cases": len(cases), "intent_ok": int(intent_ok), "slot_ok": int(slot_ok), "slot_count": slot_count,
            "mixed_ok": int(mixed_ok), "mixed_count": mixed_count}


def score_emergency() -> tuple[int, int, int, int]:
    cases = [json.loads(line) for line in (ROOT / "eval" / "emergency_cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    positives = [c for c in cases if c["expect"] == "emergency"]
    negatives = [c for c in cases if c["expect"] != "emergency"]
    return sum(is_emergency(c["text"]) for c in positives), len(positives), sum(is_emergency(c["text"]) for c in negatives), len(negatives)


def score_bp() -> tuple[int, int]:
    cases = [
        ("माझा बीपी १३२ बाय ८६", (132, 86)), ("बीपी 132/86", (132, 86)),
        ("my BP is 132 over 86", (132, 86)), ("blood pressure 120 by 80", (120, 80)),
        ("ब्लड प्रेशर १२० वर ८०", (120, 80)),
        ("माझा बीपी १३२ आहे", None), ("132 by 86", None), ("बीपी चांगला आहे", None),
        ("बीपी 30/20", None), ("उद्या १३२ ला जायचं", None),
    ]
    return sum(parse_bp(text) == expected for text, expected in cases), len(cases)


def dialogue_means() -> tuple[int, dict[str, float]]:
    if not DIALOGUE_FILE.is_file():
        return 0, {}
    data = json.loads(DIALOGUE_FILE.read_text(encoding="utf-8"))
    scores = [row["score"] for row in data.get("dialogues", {}).values() if isinstance(row.get("score"), dict)]
    dimensions = ("remembers_context", "uses_her_life", "smart_answer", "natural", "not_repetitive", "safe")
    means = {key: round(sum(score[key] for score in scores) / len(scores), 2) for key in dimensions} if scores else {}
    return len(scores), means


def fmt(value: int | float | None) -> str:
    return "n/a" if value is None else str(value)


def main() -> int:
    score = score_cases()
    emergency_ok, emergency_total, false_alarms, negative_total = score_emergency()
    bp_ok, bp_total = score_bp()
    dialogue_n, dialogue = dialogue_means()
    voice = load_voice_metrics(24)
    stages = voice["stages"]
    report = [
        "# Arjun system evaluation report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "Synthetic text regression sets and the local voice turnlog are reported below. No Prisma WER is reported; it is not measured here and publication is restricted by the project policy.",
        "",
        "## Intent and language",
        "",
        f"- Intent accuracy: {score['intent_ok']}/{score['cases']} ({score['intent_ok'] / max(1, score['cases']):.1%}).",
        f"- Reminder date/time slots: {score['slot_ok']}/{score['slot_count']}.",
        f"- Mixed Latin + Devanagari cases: {score['mixed_ok']}/{score['mixed_count']} (small synthetic subset).",
        "",
        "## Safety and readings",
        "",
        f"- Emergency recall: {emergency_ok}/{emergency_total}.",
        f"- Emergency false alarms: {false_alarms}/{negative_total}.",
        f"- BP parsing: {bp_ok}/{bp_total} synthetic accept/reject cases.",
        "- Sugar parsing: not implemented; no numerical sugar-reading parser is scored.",
        "",
        "## Dialogue memory",
        "",
        f"Stored judged dialogue set: {dialogue_n} scored dialogues from `{DIALOGUE_FILE.name}`; dimensions use a 0–2 scale except safety (0–1).",
    ]
    if dialogue:
        report.extend(["", "| Dimension | Mean |", "|---|---:|"])
        report.extend(f"| {key.replace('_', ' ')} | {value:.2f} |" for key, value in dialogue.items())
    else:
        report.append("No scored dialogue results available.")
    report.extend([
        "",
        "## Voice latency (last 24 hours)",
        "",
        "| Stage | n | p50 ms | p90 ms |",
        "|---|---:|---:|---:|",
        f"| EOS → final (STT) | {stages['stt']['count']} | {fmt(stages['stt']['p50_ms'])} | {fmt(stages['stt']['p90_ms'])} |",
        f"| Final → reasoning start | {stages['final_to_reasoning']['count']} | {fmt(stages['final_to_reasoning']['p50_ms'])} | {fmt(stages['final_to_reasoning']['p90_ms'])} |",
        f"| Reasoning done → first audio | {stages['reasoning_to_first_audio']['count']} | {fmt(stages['reasoning_to_first_audio']['p50_ms'])} | {fmt(stages['reasoning_to_first_audio']['p90_ms'])} |",
        f"| EOS → speaking | {stages['eos_to_speaking']['count']} | {fmt(stages['eos_to_speaking']['p50_ms'])} | {fmt(stages['eos_to_speaking']['p90_ms'])} |",
        f"| Barge-in start → agent stopped | {stages['barge_in_stop']['count']} | {fmt(stages['barge_in_stop']['p50_ms'])} | {fmt(stages['barge_in_stop']['p90_ms'])} |",
        "",
        f"- Completed voice turns: {voice['counts']['complete']}/{voice['counts']['turns']}; barge-ins at or below 300 ms: {fmt(stages['barge_in_stop'].get('within_300_ms'))}/{voice['counts']['barge_ins']}.",
        "- Latency values are n/a where the current local turnlog has no samples; no values are inferred.",
        "",
    ])
    target = ROOT / "eval" / "REPORT.md"
    target.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {target.relative_to(ROOT)} (numeric-only summary)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
