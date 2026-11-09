"""Call-intent eval + invalid_json rate (2026-11-09). 30 call utterances (mr / hi / en / code-mixed, STT-noisy, "again") and 8
non-calls, in two modes: rules only (no LLM) and the live hosted LLM (.env LLM_*). No key is printed. Works on older checkouts too
(the invalid_json rate comes from each turn's `route_reason`, not from newer counters).

    python scripts/eval_calls.py            # both modes
    python scripts/eval_calls.py --rules    # rules only (no network)
Accuracy = a call utterance produced a VIDEO_CALL action for the right contact; a non-call did not produce one.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "services" / "core-api"), str(ROOT / "services" / "reasoning")]
sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", action="store_true")
    ap.add_argument("--pace", type=float, default=3.0)
    a = ap.parse_args()
    try:
        from dotenv import dotenv_values

        for k, v in dotenv_values(ROOT / ".env").items():
            if v is not None:
                os.environ.setdefault(k, v)
    except ImportError:
        pass
    os.environ.update(DATABASE_URL="sqlite:///:memory:", ARJUN_TESTING="1", ARJUN_ASK_BEFORE_ACTING="0")
    for k in ("CORE_API_KEY", "TELEGRAM_ENABLED"):
        os.environ.pop(k, None)
    import httpx
    from core_api.db import Base, get_db, make_engine
    from core_api.main import app, get_now
    from fastapi.testclient import TestClient
    from reasoning_svc import config
    from reasoning_svc import turn as turn_mod
    from reasoning_svc.core_client import CoreClient
    from reasoning_svc.evon import EvonClient, load_intent_schema
    from reasoning_svc.turn import TurnEngine
    from sqlalchemy.orm import sessionmaker

    turn_mod._UNDERSTAND_TIMEOUT_S = 40.0  # a slow hosted LLM cannot fit the production 3 s; the point here is the JSON, not speed
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _db():
        with factory() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_now] = lambda: datetime.now()
    items = [json.loads(x) for x in (ROOT / "eval" / "calls_eval.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    modes = ["rules"] if a.rules else ["rules", "llm"]
    with TestClient(app) as http:
        uid = http.post("/users", json={"name": "Aaji (synthetic)", "language": "mr"}).json()["id"]
        for name, rel in (("Rahul", "son"), ("Sita", "daughter"), ("Dr Kulkarni", "doctor")):
            http.post(f"/users/{uid}/contacts", json={"name": name, "relation": rel, "phone": "00000 00000"})
        for mode in modes:
            llm = None
            if mode == "llm":
                s = config.llm_settings()
                llm = EvonClient(s.base_url, s.model, schema=load_intent_schema(), api_key=s.api_key, provider=s.provider,
                                 send_template_kwargs=s.send_template_kwargs, max_tokens=s.max_tokens, timeout_s=s.timeout_s,
                                 reasoning_off=s.reasoning_off)
                llm.http.timeout = httpx.Timeout(45.0)
                print(f"\n== LLM {s.provider}/{s.model}")
            eng = TurnEngine(CoreClient(http), llm, llm_timeout_s=60.0, ask_first=False)
            ok = invalid = claims = 0
            misses = []
            for n, it in enumerate(items):
                if llm is not None and n:
                    time.sleep(a.pace)
                res = eng.handle(uid, it["text"])
                action = res.action or {}
                is_call = action.get("type") == "call"
                good = (is_call and action.get("title") == it["contact"]) if it["expect"] == "call" else not is_call
                ok += good
                if not good:
                    misses.append((it["id"], it["text"], res.intent, res.reply[:60]))
                if res.trace.get("route_reason") == "invalid_json":
                    invalid += 1
                if it["expect"] == "call" and not is_call and ("फोन" in res.reply or "कॉल" in res.reply):
                    claims += 1  # said something about a call but placed none
            total = len(items)
            line = f"[{mode}] intent accuracy {ok}/{total} = {ok / total:.0%} | calls claimed without an action: {claims}"
            if llm is not None:
                first = getattr(llm, "usage", {}).get("json_invalid_first")
                line += f" | invalid_json turns: {invalid}/{total} = {invalid / total:.0%}"
                if first is not None:
                    line += f" | first-answer invalid {first}/{llm.usage.get('json_calls', 0)}"
            print(line)
            for m in misses:
                print("   miss:", m)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
