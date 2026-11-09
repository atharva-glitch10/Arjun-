"""Live QA eval: "can Arjun answer any question?" (2026-11-09).

Runs eval/qa/golden.jsonl through the REAL turn engine (in-process, in-memory core-api) with the real hosted LLM
(.env LLM_*), real Tavily (.env TAVILY_API_KEY) and real Open-Meteo. No key is ever printed. The family-approved news
domains for the synthetic elder are lokmat.com and loksatta.com; her city is Pune.

    python scripts/eval_qa.py                 # everything, budgets relaxed (a slow hosted LLM cannot fit 3 s / 6 s)
    python scripts/eval_qa.py --real          # production budgets (a slow LLM then falls back to the rules)
    python scripts/eval_qa.py --only roles,prices --limit 10

Prints per-category accuracy, routing accuracy, latency p50/p95 and the worst answers; writes eval/qa/last_run.jsonl and
eval/results/QA_RESULTS.md. Accuracy here = the reply contains an expected answer point (or has the expected shape),
contains no `must_not` text, and is not the "no information" / "not sure" line. It is an automatic check, not a human
review: a correct answer worded without any expected point counts as a miss, so read the worst list.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "services" / "core-api"), str(ROOT / "services" / "reasoning")]
sys.stdout.reconfigure(encoding="utf-8")


def load_env() -> None:
    try:
        from dotenv import dotenv_values
    except ImportError:  # pragma: no cover
        return
    for k, v in dotenv_values(ROOT / ".env").items():
        if v is not None:
            os.environ.setdefault(k, v)
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["ARJUN_TESTING"] = "1"
    for k in ("CORE_API_KEY", "TELEGRAM_ENABLED"):
        os.environ.pop(k, None)
    os.environ["ARJUN_ASK_BEFORE_ACTING"] = "0"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true", help="production time budgets (default: relaxed, see docstring)")
    ap.add_argument("--only", default="", help="comma-separated categories")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--pace", type=float, default=4.0, help="seconds between questions (the LLM client is limited to 60 calls/min)")
    ap.add_argument("--golden", default=str(ROOT / "eval" / "qa" / "golden.jsonl"))
    a = ap.parse_args()
    load_env()

    import httpx
    from core_api.db import Base, get_db, make_engine
    from core_api.main import app, get_now
    from fastapi.testclient import TestClient
    from reasoning_svc import config
    from reasoning_svc import replies as rp
    from reasoning_svc import turn as turn_mod
    from reasoning_svc.core_client import CoreClient
    from reasoning_svc.evon import EvonClient, load_intent_schema
    from reasoning_svc.turn import TurnEngine
    from sqlalchemy.orm import sessionmaker

    if not a.real:  # a slow hosted LLM (8-11 s per call) cannot fit the production 3 s / 6 s budgets
        turn_mod._UNDERSTAND_TIMEOUT_S = 40.0
        turn_mod._WEB_TURN_BUDGET_S = 90.0
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _db():
        with factory() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_now] = lambda: datetime.now()
    s = config.llm_settings()
    print(f"LLM: {s.provider} / {s.model} (configured={s.configured}) | budgets={'production' if a.real else 'relaxed'}")
    items = [json.loads(x) for x in Path(a.golden).read_text(encoding="utf-8").splitlines() if x.strip()]
    if a.only:
        keep = set(a.only.split(","))
        items = [i for i in items if i["cat"] in keep or i["id"] in keep]
    if a.limit:
        items = items[: a.limit]

    rows = []
    with TestClient(app) as http:
        uid = http.post("/users", json={"name": "Aaji (synthetic)", "language": "mr", "city": "Pune"}).json()["id"]
        for label, url in (("लोकमत", "https://www.lokmat.com/rss"), ("लोकसत्ता", "https://www.loksatta.com/feed")):
            http.post(f"/users/{uid}/app-links", json={"kind": "rss", "label": label, "value": url, "allow_other_host": True})
        llm = EvonClient(
            s.base_url, s.model, schema=load_intent_schema(), api_key=s.api_key, provider=s.provider,
            send_template_kwargs=s.send_template_kwargs, max_tokens=s.max_tokens, timeout_s=s.timeout_s,
            reasoning_off=s.reasoning_off,
        )
        if not a.real:
            llm.http.timeout = httpx.Timeout(45.0)
        eng = TurnEngine(CoreClient(http), llm, llm_timeout_s=60.0 if not a.real else 4.0)
        cur_lang = "mr"
        for n, it in enumerate(items, 1):
            if it["lang"] != cur_lang:
                http.patch(f"/users/{uid}", json={"language": it["lang"]})
                cur_lang = it["lang"]
            if n > 1:
                time.sleep(a.pace)
            eng.last_web = {}
            t = time.perf_counter()
            try:
                res = eng.handle(uid, it["q"])
                reply, web, intent, mode, source = res.reply, res.trace.get("web"), res.intent, res.mode, res.source
            except Exception as exc:  # noqa: BLE001
                reply, web, intent, mode, source = f"<<{type(exc).__name__}>>", "crash", "ERR", "", ""
            ms = round((time.perf_counter() - t) * 1000)
            row = judge(it, reply, web, intent, mode, source, ms, dict(eng.last_web), rp)
            rows.append(row)
            print(f"[{n}/{len(items)}] {'OK ' if row['ok'] else 'BAD'} {it['id']:6} {ms:6d} ms route={row['route']:12} {it['q'][:40]} -> {reply[:70]}", flush=True)
            out = ROOT / "eval" / "qa" / "last_run.jsonl"
            out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    report(rows, a)
    return 0


_SEARCH_WEB = {"search", "search_news", "search_unsure", "search_failed", "news_no_approved_result", "news_no_source", "cache",
               "answer_failed", "no_llm", "no_budget", "error"}


def route_of(web, intent, mode, reply_is_health) -> str:
    if web in _SEARCH_WEB:
        return "search"
    if web in ("weather", "weather_failed", "ask_city"):
        return "tool"
    if web == "blocked" or reply_is_health or mode in ("safety",) or str(intent).startswith("MED"):
        return "refuse_safe"
    if intent in ("LIST_TODAY", "GET_APPOINTMENT"):
        return "tool"
    return "know" if intent in ("CHAT", "UNKNOWN") else str(intent).lower()


def judge(it, reply, web, intent, mode, source, ms, last_web, rp) -> dict:
    lang = it["lang"] if it["lang"] in rp.R else "mr"
    none_line = rp.R[lang]["web_none"]
    unsure_prefix = rp.R[lang]["web_unsure"].split("{found}")[0].strip()
    deflect = {rp.R[lang].get(k) for k in ("web_health", "med_deflect", "med_family_sets")} - {None}
    health_line = reply in deflect or "डॉक्टर" in reply or "doctor" in reply.lower()
    route = route_of(web, intent, mode, health_line and it["route"] == "refuse_safe")
    failure = reply.strip() == none_line or (unsure_prefix and reply.startswith(unsure_prefix)) or reply.startswith("<<")
    expect = it.get("expect") or []
    bad_hits = [p for p in (it.get("must_not") or []) if re.search(p, reply, re.I)]
    shape = it.get("shape")
    hit = any(re.search(p, reply, re.I) for p in expect) if expect else None
    if it["route"] == "refuse_safe":
        ok = health_line and not bad_hits and route == "refuse_safe"
    elif failure:
        ok = False
    elif expect:
        ok = bool(hit) and not bad_hits
    elif shape == "number":
        ok = bool(re.search(r"[0-9०-९]", reply))
    elif shape in ("name", "news"):
        ok = len(reply.strip()) > 8
    else:
        ok = len(reply.strip()) > 3 and not bad_hits
    if it["route"] == "tool" and route == "tool" and web in ("weather_failed", "ask_city"):
        ok = False
    cause = ""
    if not ok:
        if web == "crash":
            cause = "crash"
        elif failure and web == "search_failed":
            cause = "no_results"
        elif failure and web == "search_unsure":
            cause = "gate_unsure (found something, could not state the fact)"
        elif failure and web in ("news_no_approved_result", "news_no_source"):
            cause = "news_no_approved_result"
        elif failure:
            cause = f"no_answer ({web})"
        elif source != "llm" and web is None and route == "know":
            cause = "llm_unavailable_rules_replied"
        elif bad_hits:
            cause = "must_not_hit (wrong or unsafe fact)"
        elif it["route"] not in ("any", route):
            cause = f"routing (expected {it['route']}, got {route})"
        else:
            cause = "wrong_or_missing_fact"
    return {
        "id": it["id"], "cat": it["cat"], "lang": it["lang"], "q": it["q"], "ok": ok, "route": route, "expected_route": it["route"],
        "route_ok": it["route"] in ("any", route), "ms": ms, "reply": reply, "web": web, "cause": cause,
        "queries": last_web.get("queries"), "top": last_web.get("top"), "engine_answer": last_web.get("answer"),
        "wrong": (not ok) and not failure and bool(expect or bad_hits),
    }


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))] if xs else 0


def report(rows, a) -> None:
    n = len(rows)
    cats = defaultdict(list)
    for r in rows:
        cats[r["cat"]].append(r)
    lines = [f"# QA eval ({datetime.now():%Y-%m-%d %H:%M}) - {n} questions, budgets={'production' if a.real else 'relaxed'}", ""]
    acc = sum(r["ok"] for r in rows) / max(1, n)
    routed = [r for r in rows if r["expected_route"] != "any"]
    rt = sum(r["route_ok"] for r in routed) / max(1, len(routed))
    lat = [r["ms"] for r in rows]
    by_route = {k: [r["ms"] for r in rows if r["route"] == k] for k in ("know", "search", "tool", "refuse_safe")}
    lines += [f"**Accuracy {acc:.0%}** ({sum(r['ok'] for r in rows)}/{n}) | **routing {rt:.0%}** ({sum(r['route_ok'] for r in routed)}/{len(routed)}) | "
              f"latency p50 {pct(lat, 50)} ms, p95 {pct(lat, 95)} ms, mean {round(statistics.mean(lat)) if lat else 0} ms",
              f"wrong/unsafe (answered, but not the expected fact): {sum(r['wrong'] for r in rows)}", "",
              "| category | n | accuracy |", "|---|---|---|"]
    for c, rs in cats.items():
        lines.append(f"| {c} | {len(rs)} | {sum(r['ok'] for r in rs) / len(rs):.0%} |")
    lines += ["", "| route | n | p50 ms | p95 ms |", "|---|---|---|---|"]
    for k, v in by_route.items():
        if v:
            lines.append(f"| {k} | {len(v)} | {pct(v, 50)} | {pct(v, 95)} |")
    worst = sorted((r for r in rows if not r["ok"]), key=lambda r: (not r["wrong"], r["id"]))[:15]
    lines += ["", f"## The {len(worst)} worst (question -> query -> top result -> reply -> cause)", ""]
    for r in worst:
        lines.append(f"- **{r['id']}** {r['q']}\n  - queries: {r['queries']}\n  - top: {(r['top'] or [None])[0]}\n"
                     f"  - reply: {r['reply'][:160]}\n  - cause: {r['cause']}")
    text = "\n".join(lines)
    print("\n" + text)
    (ROOT / "eval" / "results").mkdir(parents=True, exist_ok=True)
    (ROOT / "eval" / "results" / "QA_RESULTS.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
