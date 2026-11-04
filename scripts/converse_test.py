"""Multi-turn context probe: runs scripted dialogues through the real reasoning /turn endpoint and prints, for every
turn, the exact messages[] that reached the LLM (redacted) plus Arjun's reply.

Everything runs IN PROCESS (reasoning's FastAPI app + the real core-api app on an in-memory SQLite database, with a
synthetic user), so no repository file, log or database is touched. The LLM is whatever the root .env configures
(LLM_* or SARVAM_*); its key is read here, sent only to that provider and never printed. With no key the LLM is
absent and only the rule path runs (the report then says so).

Usage:
  python scripts/converse_test.py                 # the four STEP 1 dialogues
  python scripts/converse_test.py --only a,c      # a subset
  python scripts/converse_test.py --full-system   # also print the whole system prompt of every LLM call
  python scripts/converse_test.py --json out.json # machine-readable transcript (used by eval_dialogues.py)

The Harness class is reused by scripts/eval_dialogues.py.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
START = datetime.now().replace(hour=13, minute=10, second=0, microsecond=0)  # today, just after lunch time
# (today, not a fixed date: core-api stamps rows with the machine clock, and an action stamped "in the past" would expire)
SYNTHETIC_USER = {
    "name": "सुनीता (synthetic)", "honorific": "ताई", "language": "mr", "age": 74,
    "interests": ["भजन", "बागकाम", "नातवंडं"], "daily_checkins": True, "consent_distress_alert": True,
    "wake_time": "06:30", "breakfast_time": "08:00", "lunch_time": "13:00", "dinner_time": "20:00",
    "opener_start": "07:00", "opener_end": "21:00",
}
SYNTHETIC_CONTACTS = (
    {"name": "राहुल", "relation": "मुलगा", "phone": "0000000001"},
    {"name": "नेहा", "relation": "मुलगी", "phone": "0000000002"},
)


def load_dotenv() -> dict[str, str]:
    path = Path(os.environ.get("ARJUN_DOTENV") or ROOT / ".env")
    out: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def redact(text: str) -> str:
    """No phone-number-like digit runs and no key-shaped tokens in any printed text."""
    text = re.sub(r"\d{6,}", "<digits>", text)
    return re.sub(r"\b(?:sk|AIza|AC)[-_A-Za-z0-9]{12,}\b", "<secret>", text)


class Harness:
    """One synthetic household: a user, a simulated clock, the real engine, and a spy on the LLM requests."""

    def __init__(self, *, max_tokens: int = 250, llm: bool = True, engine_kwargs: dict[str, Any] | None = None) -> None:
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        os.environ.pop("CORE_API_KEY", None)
        os.environ["ARJUN_TESTING"] = "1"
        os.environ["ARJUN_ASK_BEFORE_ACTING"] = "0"
        for name in ("TELEGRAM_ENABLED", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "BASE_URL", "JOIN_SECRET"):
            os.environ.pop(name, None)
        sys.path[:0] = [str(ROOT / "services" / "core-api"), str(ROOT / "services" / "reasoning")]

        import httpx
        from core_api.db import Base, get_db, make_engine
        from core_api.main import app as core_app
        from core_api.main import get_now
        from fastapi.testclient import TestClient
        from reasoning_svc import config
        from reasoning_svc import main as rmain
        from reasoning_svc.core_client import CoreClient
        from reasoning_svc.evon import EvonClient, Limiter
        from reasoning_svc.ratelimit import TokenBucket
        from reasoning_svc.turn import TurnEngine
        from sqlalchemy.orm import sessionmaker

        self.now = START
        import core_api.models as core_models

        self._core_models = core_models
        self._real_local_now = core_models.local_now
        core_models.local_now = lambda: self.now  # rows are stamped with the SIMULATED clock, like get_now
        self.llm_requests: list[dict[str, Any]] = []
        engine = make_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        def _db():  # type: ignore[no-untyped-def]
            with factory() as s:
                yield s

        core_app.dependency_overrides[get_db] = _db
        core_app.dependency_overrides[get_now] = lambda: self.now
        self._core_app = core_app
        self.core_http = TestClient(core_app)
        self.core_http.__enter__()

        settings = config.llm_settings({**load_dotenv(), "LLM_MAX_TOKENS": str(max_tokens)})
        self.provider = settings.provider if (llm and settings.configured) else "none (rules only)"

        def spy(request: httpx.Request) -> None:
            try:
                self.llm_requests.append(json.loads(request.content))
            except ValueError:
                pass

        client = None
        if llm and settings.configured:
            headers = {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}
            http = httpx.Client(timeout=30.0, headers=headers, event_hooks={"request": [spy]})
            client = EvonClient(
                settings.base_url, settings.model, http=http, api_key="", provider=settings.provider,
                send_template_kwargs=settings.send_template_kwargs, max_tokens=settings.max_tokens,
                reasoning_off=settings.reasoning_off, limiter=Limiter(8, 600),
            )
        self.sim_mono = lambda: 1000.0 + (self.now - START).total_seconds()
        kwargs: dict[str, Any] = {
            "clock": lambda: self.now, "mono": self.sim_mono, "ask_first": False, "llm_timeout_s": 25.0,
        }
        kwargs.update(engine_kwargs or {})
        self.engine = TurnEngine(CoreClient(self.core_http), client, **kwargs)
        rmain._engine = self.engine
        rmain._tracker = None
        rmain._turn_bucket = TokenBucket(1000.0, 1000)
        self.rmain = rmain
        self.api = TestClient(rmain.app)
        r = self.core_http.post("/users", json=SYNTHETIC_USER)
        r.raise_for_status()
        self.uid = int(r.json()["id"])
        for c in SYNTHETIC_CONTACTS:
            self.core_http.post(f"/users/{self.uid}/contacts", json=c).raise_for_status()
        self.transcript: list[dict[str, Any]] = []

    # ---- time -----------------------------------------------------------------------------------------------
    def advance(self, minutes: float = 0.0, days: int = 0) -> None:
        self.now += timedelta(minutes=minutes, days=days)

    def flush_conversations(self) -> int:
        """What the scheduler does every tick: end quiet conversations (summary + life facts)."""
        return int(self.rmain.get_tracker().flush_idle(self.now))

    # ---- turns ----------------------------------------------------------------------------------------------
    def say(self, text: str) -> dict[str, Any]:
        before = len(self.llm_requests)
        r = self.api.post("/turn", json={"user_id": self.uid, "text": text})
        r.raise_for_status()
        out = r.json()
        calls = self.llm_requests[before:]
        rec = {
            "at": self.now.isoformat(timespec="minutes"), "who": "user", "text": text, "reply": out["reply"],
            "intent": out["intent"], "mode": out["mode"], "source": out["source"], "llm_calls": calls,
        }
        self.transcript.append(rec)
        self.advance(minutes=0.5)
        return rec

    def checkin(self, kind: str = "lunch") -> dict[str, Any]:
        """An assistant-initiated check-in: queued by core-api, claimed and 'spoken' through the real delivery path."""
        http = self.core_http
        uid = self.uid
        real = self.now
        self.now = real.replace(hour=6, minute=0)
        rows = {c["kind"]: c for c in http.get(f"/users/{uid}/checkins").json()}
        due = datetime.fromisoformat(rows[kind]["due_at"])
        self.now = due
        for other, row in rows.items():  # whatever was due earlier has been told already
            if other != kind and datetime.fromisoformat(row["due_at"]) < due:
                http.post(f"/users/{uid}/checkins/volunteer", json={"topic": other, "answer": "done"})
        http.post("/internal/checkins/tick").raise_for_status()
        self.now = real
        self.advance(minutes=5)  # she has been quiet for a while: the question is not postponed
        item = self.engine.deliver_next(uid, "sess-1")
        if item is None:
            raise RuntimeError(f"no {kind} check-in was delivered")
        self.engine.deliver_spoken(uid, item["delivery_id"], "sess-1")
        rec = {
            "at": self.now.isoformat(timespec="minutes"), "who": "arjun-initiated", "text": "", "reply": item["text"],
            "intent": "CHECKIN_ASKED", "mode": "care", "source": "rules", "llm_calls": [],
        }
        self.transcript.append(rec)
        self.advance(minutes=0.5)
        return rec

    def close(self) -> None:
        self._core_models.local_now = self._real_local_now
        self.core_http.__exit__(None, None, None)
        self._core_app.dependency_overrides.clear()


# ---- the four STEP 1 dialogues -------------------------------------------------------------------------------------
DIALOGUES: dict[str, dict[str, Any]] = {
    "a": {
        "title": "a) grandson: name, then a question that needs the name",
        "steps": [
            {"say": "आज माझा नातू आला होता"}, {"say": "त्याचं नाव आर्यन"},
            {"say": "तो कितवीत आहे विचार ना"}, {"say": "तुला त्याचं नाव आठवतंय का?"},
        ],
        "probe": "आर्यन",  # must be visible to the LLM on the last turn
    },
    "b": {
        "title": "b) check-in asked by Arjun, then 'what did you ask me?'",
        "steps": [
            {"checkin": "lunch"}, {"say": "हो, वरण भात"}, {"say": "आणि तू काय विचारलं होतंस?"},
        ],
        "probe": "जेवण",
    },
    "c": {
        "title": "c) an action (bhajan), a refusal, then 'what did I say?'",
        "steps": [
            {"say": "मला भजन ऐकायचं आहे"}, {"say": "नको, आधी बोलूया"}, {"say": "मी काय म्हणाले होते?"},
        ],
        "probe": "भजन",
    },
    "d": {
        "title": "d) a 4-minute pause, then 'what were we talking about?'",
        "steps": [
            {"say": "आज सकाळी मी बागेत तुळशीला पाणी घातलं आणि गुलाबाची फुलं पाहिली"},
            {"say": "त्या गुलाबाच्या झाडाला खूप कळ्या आल्या आहेत"},
            {"pause": 4}, {"say": "आपण कशाबद्दल बोलत होतो?"},
        ],
        "probe": "गुलाब",
    },
}


def run_dialogue(h: Harness, spec: dict[str, Any]) -> list[dict[str, Any]]:
    start = len(h.transcript)
    for step in spec["steps"]:
        if "say" in step:
            h.say(step["say"])
        elif "checkin" in step:
            h.checkin(step["checkin"])
        elif "pause" in step:
            h.advance(minutes=step["pause"])
        elif "day" in step:
            h.flush_conversations()
            h.advance(days=step["day"])
        elif "flush" in step:
            h.advance(minutes=step["flush"])
            h.flush_conversations()
    return h.transcript[start:]


def show(rec: dict[str, Any], full_system: bool) -> None:
    who = "ARJUN (on his own)" if rec["who"] == "arjun-initiated" else f"HER   : {rec['text']}"
    print(f"\n  [{rec['at']}] {who}")
    for i, call in enumerate(rec["llm_calls"], 1):
        msgs = call.get("messages", [])
        kind = "json" if call.get("response_format") else "chat"
        print(f"    LLM call {i} ({kind}, temp {call.get('temperature')}): {len(msgs)} messages")
        for m in msgs:
            content = redact(str(m.get("content", "")))
            if m.get("role") == "system" and not full_system:
                flags = [n for n in ("USER CONTEXT", "THIS SESSION", "OPEN QUESTION", "WHAT SHE TOLD") if n in content]
                print(f"      system: {len(content)} chars; blocks: {', '.join(flags) or 'none'}; starts: {content[:90]!r}")
            else:
                print(f"      {m.get('role')}: {content}")
    if not rec["llm_calls"]:
        print("    (no LLM call: rules answered)")
    print(f"    ARJUN : {rec['reply']}   [{rec['intent']}/{rec['source']}]")


def context_seen(rec: dict[str, Any], probe: str) -> bool:
    """Did the LLM on this turn see the probe word anywhere in its prompt?"""
    return any(probe in str(m.get("content", "")) for c in rec["llm_calls"] for m in c.get("messages", []))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--full-system", action="store_true")
    ap.add_argument("--json", default="")
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    chosen = [k for k in DIALOGUES if not args.only or k in args.only.split(",")]
    results: dict[str, Any] = {}
    verdicts: list[str] = []
    for key in chosen:
        spec = DIALOGUES[key]
        h = Harness(llm=not args.no_llm)
        try:
            print(f"\n=== {spec['title']}   (LLM: {h.provider})")
            rows = run_dialogue(h, spec)
            for rec in rows:
                show(rec, args.full_system)
            last = rows[-1]
            seen = context_seen(last, spec["probe"])
            verdicts.append(f"{key}: last turn LLM saw '{spec['probe']}': {'YES' if seen else 'NO'} (LLM calls: {len(last['llm_calls'])})")
            results[key] = {"title": spec["title"], "turns": rows, "probe_seen": seen}
        finally:
            h.close()
    print("\n=== VERDICT")
    for v in verdicts:
        print("  " + v)
    if args.json:
        Path(args.json).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
