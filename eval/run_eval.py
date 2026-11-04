"""Text-level eval of the rule-based parser + distress check against eval/cases.jsonl.

Measures intent accuracy, slot accuracy (date/time on cases that specify them) and distress recall.
WER and latency need real audio / a live stack and are NOT measured here (no numbers invented).
Cases are synthetic and small - treat results as a regression check, not a benchmark.

Usage: python eval/run_eval.py
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "reasoning"))

from reasoning_svc.distress import is_distress, is_emergency  # noqa: E402
from reasoning_svc.parser import Profile, parse  # noqa: E402

NOW = datetime(2026, 10, 6, 9, 0)


def predict(text: str) -> tuple[str, str | None, str | None, bool]:
    if is_distress(text):
        return "DISTRESS", None, None, False
    p = parse(text, Profile(), NOW, "mr", has_pending=False)
    d = p.draft
    if p.intent == "CREATE_REMINDER" and d.missing() == "ampm":
        return p.intent, d.date, None, True
    return p.intent, d.date, d.time, False


def main() -> int:
    cases = [json.loads(line) for line in (Path(__file__).parent / "cases.jsonl").open(encoding="utf-8") if line.strip()]
    intent_ok = slot_total = slot_ok = 0
    distress_total = distress_hit = 0
    misses: list[str] = []
    for c in cases:
        intent, date, time_, ambiguous = predict(c["text"])
        if intent == c["intent"]:
            intent_ok += 1
        else:
            misses.append(f"intent: {c['text']!r} expected {c['intent']} got {intent}")
        if c["intent"] == "DISTRESS":
            distress_total += 1
            distress_hit += intent == "DISTRESS"
        if "date_offset" in c:
            slot_total += 1
            want_date = (NOW.date() + timedelta(days=c["date_offset"])).isoformat()
            ok = date == want_date and time_ == c.get("time") and ambiguous == c.get("time_ambiguous", False)
            slot_ok += ok
            if not ok:
                misses.append(f"slots: {c['text']!r} expected {want_date} {c.get('time')} got {date} {time_}")
    n = len(cases)
    print(f"cases: {n}")
    print(f"intent accuracy: {intent_ok}/{n}")
    print(f"slot accuracy:   {slot_ok}/{slot_total}")
    print(f"distress recall: {distress_hit}/{distress_total}")
    emergency = [json.loads(line) for line in (Path(__file__).parent / "emergency_cases.jsonl").open(encoding="utf-8") if line.strip()]
    must = [c for c in emergency if c["expect"] == "emergency"]
    harmless = [c for c in emergency if c["expect"] != "emergency"]
    emergency_hit = sum(is_emergency(c["text"]) for c in must)
    false_alarm = [c["text"] for c in harmless if is_emergency(c["text"])]
    print(f"emergency recall (rules only, loanwords + STT spellings): {emergency_hit}/{len(must)}")
    print(f"harmless sentences flagged as emergency:                  {len(false_alarm)}/{len(harmless)}")
    print("WER / latency: not measured (needs audio + live stack)")
    for m in misses:
        print("  MISS", m)
    for c in must:
        if not is_emergency(c["text"]):
            print("  MISS emergency:", c["text"])
    for t in false_alarm:
        print("  FALSE ALARM:", t)
    return 0 if distress_hit == distress_total and emergency_hit == len(must) and not false_alarm else 1


if __name__ == "__main__":
    raise SystemExit(main())
