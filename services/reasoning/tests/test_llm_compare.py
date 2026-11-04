"""eval/llm_compare.py: the scoring is tested against a fake client, so a real run can be trusted."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def load():
    spec = importlib.util.spec_from_file_location("llm_compare", ROOT / "eval" / "llm_compare.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = load()


class Fake:
    provider, model = "FakeAI", "fake-1"

    def __init__(self, intents=None, replies=None):
        self.intents = intents or {}
        self.replies = replies or {}
        self.usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
        self.clock = 0.0

    def extract_intent(self, text, language, now, wake, lunch, dinner, timeout=None):
        self.usage["calls"] += 1
        self.usage["prompt_tokens"] += 100
        self.usage["completion_tokens"] += 10
        self.clock += 0.5
        got = self.intents.get(text, "CHAT")
        return None if got is None else {"intent": got, "confidence": 0.9, "language": "mr"}

    def companion_reply(self, text, language, now=None, history=None, interests=None, timeout=None):
        self.usage["calls"] += 1
        self.usage["prompt_tokens"] += 80
        self.usage["completion_tokens"] += 20
        self.clock += 1.5
        return self.replies.get(text, "छान वाटलं. मग पुढे काय झालं?")


def test_sentence_set_is_twenty_real_first_then_distinct_eval_cases(tmp_path):
    private = tmp_path / "private"
    private.mkdir()
    with (private / "real_speech_x.jsonl").open("w", encoding="utf-8") as f:
        for i in range(14):
            f.write(json.dumps({"text": f"खरं वाक्य {i}", "intent": "LIST_TODAY" if i % 2 else None}) + "\n")
    cases = tmp_path / "cases.jsonl"
    cases.write_text(
        "\n".join(json.dumps(c) for c in (
            {"text": "a1", "intent": "CREATE_REMINDER"}, {"text": "a2", "intent": "CREATE_REMINDER"},
            {"text": "b1", "intent": "LIST_TODAY"}, {"text": "c1", "intent": "GET_APPOINTMENT"},
            {"text": "d1", "intent": "CALL_FAMILY_REMINDER"}, {"text": "e1", "intent": "REQUEST_CAREGIVER"},
            {"text": "f1", "intent": "MEDICAL_QUESTION"}, {"text": "g1", "intent": "DISTRESS"},
        )),
        encoding="utf-8",
    )
    rows = mod.build_sentences(private, cases, total=20)
    assert len(rows) == 20 and [r["source"] for r in rows[:14]] == ["real"] * 14
    cased = [r["text"] for r in rows[14:]]
    assert cased[0] == "a1" and "a2" not in cased  # one per intent, so the set is varied
    assert len(set(cased)) == 6


def test_sentences_fall_back_to_cases_when_no_real_speech_is_present(tmp_path):
    cases = tmp_path / "cases.jsonl"
    cases.write_text("\n".join(json.dumps({"text": f"t{i}", "intent": f"I{i}"}) for i in range(30)), encoding="utf-8")
    rows = mod.build_sentences(tmp_path / "nope", cases, total=20)
    assert len(rows) == 20 and {r["source"] for r in rows} == {"case"}


def test_ten_companion_prompts_cover_the_boundary_traps():
    assert len(mod.COMPANION_PROMPTS) == 10
    traps = {p["trap"] for p in mod.COMPANION_PROMPTS}
    assert {"recipe", "fact", "medical", "human", "missed_you"} <= traps


def test_intent_scoring_counts_valid_json_accuracy_and_skips_unscorable():
    sentences = [
        {"text": "s1", "expected": "LIST_TODAY", "source": "real"},
        {"text": "s2", "expected": "CREATE_REMINDER", "source": "real"},
        {"text": "s3", "expected": "GREETING", "source": "real"},  # a rules-only intent: not in the schema
        {"text": "s4", "expected": None, "source": "real"},  # unlabelled
        {"text": "s5", "expected": "GET_APPOINTMENT", "source": "case"},
    ]
    fake = Fake(intents={"s1": "LIST_TODAY", "s2": "CHAT", "s3": "CHAT", "s4": "CHAT", "s5": None})
    rows = mod.run_intents(fake, sentences, timer=lambda: fake.clock)
    s = mod.summarize(rows, [], fake.usage)
    assert s["json_valid"] == {"valid": 4, "total": 5, "pct": 80.0}
    assert s["intent_accuracy"] == {"correct": 1, "scored": 3, "pct": pytest.approx(33.3, abs=0.1)}


def test_latency_tokens_and_medians():
    fake = Fake()
    rows = mod.run_intents(fake, [{"text": f"s{i}", "expected": None, "source": "real"} for i in range(3)],
                           timer=lambda: fake.clock)
    comp = mod.run_companion(fake, mod.COMPANION_PROMPTS[:3], timer=lambda: fake.clock)
    s = mod.summarize(rows, comp, fake.usage)
    assert s["median_latency_ms"] == {"intent": 500, "companion": 1500, "all": 1000}
    assert s["total_tokens"] == {"prompt": 3 * 100 + 3 * 80, "completion": 3 * 10 + 3 * 20,
                                 "total": 3 * 110 + 3 * 100, "calls": 6}


def test_boundary_report_flags_each_category_and_counts_clean_replies():
    prompts = mod.COMPANION_PROMPTS[:5]
    bad = {
        prompts[0]["text"]: "मी माणूस आहे.",
        prompts[1]["text"]: "रोज 500 mg घ्या.",
        prompts[2]["text"]: "एक. दोन. तीन. चार. पाच.",
        prompts[3]["text"]: "That sounds nice. Tell me more.",
    }
    fake = Fake(replies=bad)
    comp = mod.run_companion(fake, prompts, timer=lambda: fake.clock)
    s = mod.summarize([], comp, fake.usage)
    b = s["boundary"]
    assert b["n"] == 5 and b["clean"] == 1 and b["clean_pct"] == 20.0
    assert b["violations"] == {"human": 1, "medical": 1, "sentences": 1, "script": 1}


def test_main_without_a_provider_names_what_is_missing_and_never_prints_a_key(capsys, monkeypatch, tmp_path):
    for name in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY", "EVON_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    code = mod.main(["--env-file", str(tmp_path / "missing.env")])
    out = capsys.readouterr().out
    assert code == 2 and "LLM_BASE_URL" in out and "LLM_MODEL" in out
