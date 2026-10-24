"""Regression on the speaker's own transcripts (eval/private is git-ignored: real speech).

Cases with `intent: null` are skipped until the speaker says what they meant (turns 5 and 12 of
the 2026-10-24 session). When eval/private is absent (a fresh clone) the whole file is skipped.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from reasoning_svc.parser import Profile, parse

PRIVATE = Path(__file__).resolve().parents[3] / "eval" / "private"
NOW = datetime(2026, 10, 6, 9, 0)


def _cases():
    out = []
    for f in sorted(PRIVATE.glob("real_speech_*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            c = json.loads(line)
            if c.get("intent"):
                out.append(pytest.param(c, id=f"{f.stem}-turn{c['turn']}"))
    return out


CASES = _cases()


@pytest.mark.skipif(not CASES, reason="eval/private has no labelled real-speech cases here")
@pytest.mark.parametrize("case", CASES)
def test_real_transcript_gets_the_expected_intent_and_slots(case):
    p = parse(case["text"], Profile(), NOW, "mr", has_pending=bool(case.get("has_pending")),
              pending_action=case.get("has_pending"))
    assert p.intent == case["intent"], case["text"]
    if "time" in case:
        assert p.draft.time == case["time"]
    if "date_offset" in case:
        assert p.draft.date == (NOW.date() + timedelta(days=case["date_offset"])).isoformat()
