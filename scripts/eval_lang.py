"""Reply-language eval (2026-11-10): 20 mixed-language turns through the REAL turn engine with the live hosted LLM (.env LLM_*).
For each turn: did the reply TEXT come out in the language that was expected, and is the TTS language (the `language` the
voice-agent turns into a Timbre locale) right? Scoring uses shared/langid.py for both checkouts, so before / after compare fairly.
No key is printed.

    python scripts/eval_lang.py [eval/lang_forced.jsonl]
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "services" / "core-api"), str(ROOT / "services" / "reasoning")]
sys.stdout.reconfigure(encoding="utf-8")
LOCALE = {"mr": "mr-IN", "hi": "hi-IN", "en": "en-IN", "ta": "ta-IN", "te": "te-IN", "kn": "kn-IN", "ml": "ml-IN", "bn": "bn-IN", "gu": "gu-IN", "pa": "pa-IN"}
SCORER = Path(os.environ.get("ARJUN_SCORER", ROOT / "shared" / "langid.py"))


def main() -> int:
    from dotenv import dotenv_values

    for k, v in dotenv_values(ROOT / ".env").items():
        if v is not None:
            os.environ.setdefault(k, v)
    os.environ.update(DATABASE_URL="sqlite:///:memory:", ARJUN_TESTING="1", ARJUN_ASK_BEFORE_ACTING="0")
    for k in ("CORE_API_KEY", "TELEGRAM_ENABLED"):
        os.environ.pop(k, None)
    spec = importlib.util.spec_from_file_location("scorer_langid", SCORER)
    scorer = importlib.util.module_from_spec(spec)
    sys.modules["scorer_langid"] = scorer  # a dataclass needs its module registered
    spec.loader.exec_module(scorer)  # type: ignore[union-attr]

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

    turn_mod._UNDERSTAND_TIMEOUT_S = 40.0
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _db():
        with factory() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_now] = lambda: datetime.now()
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "eval" / "lang_eval.jsonl"  # lang_forced.jsonl: the frontend language is sent as reply_language
    items = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    s = config.llm_settings()
    print(f"LLM {s.provider}/{s.model} | code: {ROOT}")
    rows = []
    with TestClient(app) as http:
        by_scn: dict[str, list[dict]] = defaultdict(list)
        for it in items:
            by_scn[it["scenario"]].append(it)
        first = True
        for turns in by_scn.values():
            uid = http.post("/users", json={"name": "Aaji (synthetic)", "language": turns[0]["profile"]}).json()["id"]
            llm = EvonClient(s.base_url, s.model, schema=load_intent_schema(), api_key=s.api_key, provider=s.provider,
                             send_template_kwargs=s.send_template_kwargs, max_tokens=s.max_tokens, timeout_s=s.timeout_s, reasoning_off=s.reasoning_off)
            llm.http.timeout = httpx.Timeout(45.0)
            eng = TurnEngine(CoreClient(http), llm, llm_timeout_s=60.0, ask_first=False)  # a fresh session per scenario
            for it in turns:
                if not first:
                    time.sleep(3.0)
                first = False
                res = eng.handle(uid, it["text"], reply_language=it.get("ui"))
                text_lang = scorer.classify(res.reply, default=it["expect"]).lang
                text_ok = scorer.matches(res.reply, it["expect"]) and text_lang in (it["expect"], "")
                tts_ok = LOCALE.get(res.language or "") == LOCALE[it["expect"]]
                rows.append({**it, "reply": res.reply, "text_lang": text_lang, "tts_lang": res.language, "text_ok": text_ok, "tts_ok": tts_ok})
                print(f"{'OK ' if text_ok and tts_ok else 'BAD'} [{it['scenario']}] expect={it['expect']} text={text_lang:3} tts={res.language:3} | {it['text'][:34]} -> {res.reply[:60]}", flush=True)
    n = len(rows)
    print(f"\nreply TEXT language accuracy: {sum(r['text_ok'] for r in rows)}/{n} = {sum(r['text_ok'] for r in rows) / n:.0%}")
    print(f"TTS language accuracy:        {sum(r['tts_ok'] for r in rows)}/{n} = {sum(r['tts_ok'] for r in rows) / n:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
