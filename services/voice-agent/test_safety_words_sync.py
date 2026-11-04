"""safety_words.py is GENERATED from reasoning's distress.py (scripts/gen_safety_words.py).

These tests fail when the two drift: a stale generated file, or an emergency phrase that one side detects and the
other does not. The reasoning package is imported by path for the test only; the agent itself never imports it.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "reasoning"))

import safety_words  # noqa: E402
from reasoning_svc import distress  # noqa: E402

CASES = [
    json.loads(line)
    for line in (ROOT / "eval" / "emergency_cases.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]
EMERGENCY = [c["text"] for c in CASES if c["expect"] == "emergency"]
NOT_EMERGENCY = [c["text"] for c in CASES if c["expect"] == "not_emergency"]


def _generator():
    spec = importlib.util.spec_from_file_location("gen_safety_words", ROOT / "scripts" / "gen_safety_words.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_generated_file_is_up_to_date():
    gen = _generator()
    assert safety_words.__file__ is not None
    assert Path(safety_words.__file__).read_text(encoding="utf-8") == gen.render(), (
        "safety_words.py is stale: run `python scripts/gen_safety_words.py`"
    )


def test_the_phrase_lists_are_the_same_objects_of_truth():
    assert safety_words.EMERGENCY_PHRASES == distress.EMERGENCY_PHRASES
    assert safety_words.DISTRESS_PHRASES == distress.DISTRESS_PHRASES


@pytest.mark.parametrize("text", EMERGENCY)
def test_every_eval_emergency_is_detected_by_both(text):
    assert distress.is_emergency(text), f"reasoning missed: {text}"
    assert safety_words.is_emergency(text), f"voice-agent missed: {text}"
    assert safety_words.is_safety_phrase(text), f"media mode would swallow: {text}"


@pytest.mark.parametrize("text", NOT_EMERGENCY)
def test_both_sides_agree_on_the_eval_non_emergencies(text):
    assert safety_words.is_emergency(text) == distress.is_emergency(text)
