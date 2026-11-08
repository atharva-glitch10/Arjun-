"""Live web search (Brave) + weather (Open-Meteo). The network is always mocked.

Boundaries: 8 (safety runs first and never searches), 5/6 (no medical or dose lookups), 14 (never claim an answer we
did not get: any failure is the fixed "no information" line), 12 (the Brave key is never logged).
"""

import json
import logging
import os
import statistics
import time
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from reasoning_svc import replies as rp
from reasoning_svc.core_client import CoreClient
from reasoning_svc.evon import EvonClient, load_intent_schema
from reasoning_svc.tools import weather, web_search
from reasoning_svc.turn import TurnEngine

NOW = datetime(2026, 10, 6, 9, 0)
KEY = "brave-test-key-123456"
EVAL = Path(__file__).resolve().parents[3] / "eval" / "web_eval.jsonl"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    web_search.reset()
    monkeypatch.setenv("BRAVE_API_KEY", KEY)
    yield
    web_search.reset()


def brave_body(n=4):
    return {"web": {"results": [
        {"title": f"T{i} <strong>x</strong>", "description": f"snippet &amp; {i} <b>bold</b>", "url": f"https://e.test/{i}"}
        for i in range(n)
    ]}}


class Clock:
    def __init__(self):
        self.t = 100.0
        self.slept = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


# ---- the tool ---------------------------------------------------------------------------------------
def test_success_returns_top_three_cleaned_and_sends_key_and_params():
    seen = []

    def h(req):
        seen.append(req)
        return httpx.Response(200, json=brave_body())

    c = Clock()
    out = web_search.search("पुणे बातम्या", "mr", client=client(h), clock=c, sleep=c.sleep)
    assert out == [{"title": f"T{i} x", "snippet": f"snippet & {i} bold"} for i in range(3)]
    req = seen[0]
    assert req.headers["x-subscription-token"] == KEY
    q = dict(req.url.params)
    assert q["q"] == "पुणे बातम्या" and q["count"] == "3" and q["country"] == "IN" and q["search_lang"] == "mr"


def test_second_identical_query_is_served_from_cache_for_ten_minutes():
    n = []

    def h(req):
        n.append(1)
        return httpx.Response(200, json=brave_body())

    c = Clock()
    http = client(h)
    web_search.search("score", "en", client=http, clock=c, sleep=c.sleep)
    c.t += 599
    assert web_search.search("score", "en", client=http, clock=c, sleep=c.sleep) is not None
    assert len(n) == 1
    c.t += 5
    web_search.search("score", "en", client=http, clock=c, sleep=c.sleep)
    assert len(n) == 2


def test_timeout_is_retried_once_then_none():
    n = []

    def h(req):
        n.append(1)
        raise httpx.ReadTimeout("slow")

    c = Clock()
    assert web_search.search("q", "mr", client=client(h), clock=c, sleep=c.sleep) is None
    assert len(n) == 2


def test_429_then_200_succeeds_on_the_retry():
    codes = iter([429, 200])

    def h(req):
        code = next(codes)
        return httpx.Response(code, json=brave_body() if code == 200 else {})

    c = Clock()
    assert web_search.search("q", "mr", client=client(h), clock=c, sleep=c.sleep) is not None


def test_no_key_returns_none_without_any_request(monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY")

    def h(req):
        raise AssertionError("no request without a key")

    assert web_search.search("q", "mr", client=client(h)) is None
    assert web_search.available() is False


@pytest.mark.parametrize("status", [401, 403, 422])
def test_client_errors_are_none_and_not_retried(status):
    n = []

    def h(req):
        n.append(1)
        return httpx.Response(status, json={})

    c = Clock()
    assert web_search.search("q", "mr", client=client(h), clock=c, sleep=c.sleep) is None
    assert len(n) == 1


def test_rate_limit_spaces_distinct_queries_one_second_apart():
    def h(req):
        return httpx.Response(200, json=brave_body())

    c = Clock()
    http = client(h)
    web_search.search("one", "mr", client=http, clock=c, sleep=c.sleep)
    web_search.search("two", "mr", client=http, clock=c, sleep=c.sleep)
    assert c.slept and c.slept[0] == pytest.approx(1.0)


def test_rate_limit_that_cannot_fit_the_budget_is_none_without_a_request():
    n = []

    def h(req):
        n.append(1)
        return httpx.Response(200, json=brave_body())

    c = Clock()
    http = client(h)
    web_search.search("one", "mr", client=http, clock=c, sleep=c.sleep)
    assert web_search.search("two", "mr", client=http, clock=c, sleep=c.sleep, timeout_s=0.5) is None
    assert len(n) == 1


def test_the_key_is_never_logged(caplog):
    caplog.set_level(logging.DEBUG)

    def h(req):
        return httpx.Response(500)

    c = Clock()
    web_search.search("q", "mr", client=client(h), clock=c, sleep=c.sleep)
    assert KEY not in caplog.text


def test_weather_sentence_from_open_meteo():
    def h(req):
        if "geocoding" in str(req.url):
            return httpx.Response(200, json={"results": [{"latitude": 18.5, "longitude": 73.8}]})
        return httpx.Response(200, json={
            "current": {"temperature_2m": 27.4, "weather_code": 3},
            "daily": {"temperature_2m_max": [31.2], "temperature_2m_min": [22.1], "precipitation_probability_max": [40]},
        })

    out = weather.current_weather("Pune", "mr", client=client(h))
    assert out == "Puneमध्ये आत्ता ढगाळ आहे, तापमान 27 अंश. आज 22 ते 31 अंश, पावसाची शक्यता 40 टक्के."
    assert weather.current_weather("Pune", "mr", client=client(lambda r: httpx.Response(500))) is None


# ---- the engine --------------------------------------------------------------------------------------
def _understand(case_or_none=None, *, web=True, query="q", intent="chat"):
    return {
        "intent": intent,
        "slots": {"task": None, "date": None, "time": None, "time_ambiguous": False, "query": None, "media_kind": None,
                  "media_specific": False, "control": None, "contact": None, "confirm": None, "choice": None,
                  "checkin_answer": None, "bp": None},
        "reply": "" if web else "छान.",
        "confidence": 0.9,
        "needs_web": web,
        "web_query": query if web else None,
    }


class Llm:
    def __init__(self, payload, answer="संसदेत चर्चा सुरू आहे."):
        self.payload, self.answer, self.calls = payload, answer, []

    def __call__(self, req):
        body = json.loads(req.content)
        system = body["messages"][0]["content"]
        self.calls.append((system, body["messages"][-1]["content"]))

        def r(c):
            return httpx.Response(200, json={"choices": [{"message": {"content": c}}]})

        if "Return ONLY one JSON object" in system:
            return r(json.dumps(self.payload))
        if "SEARCH RESULTS" in system:
            return r(self.answer)
        return r("ठीक आहे.")

    @property
    def web_calls(self):
        return [c for c in self.calls if "SEARCH RESULTS" in c[0]]


def make(core_http, llm):
    http = httpx.Client(transport=httpx.MockTransport(llm))
    evon = EvonClient("https://llm.test/v1", "m", http=http, schema=load_intent_schema(), provider="T")
    return TurnEngine(CoreClient(core_http), evon, clock=lambda: NOW)


@pytest.fixture()
def brave(monkeypatch):
    calls = []

    def fake(query, lang="mr", **kw):
        calls.append((query, lang))
        return [{"title": "बातमी", "snippet": "संसदेत चर्चा सुरू आहे."}]

    monkeypatch.setattr(web_search, "search", fake)
    return calls


def test_needs_web_searches_speaks_a_filler_and_answers_from_snippets(core_http, uid, brave):
    llm = Llm(_understand(query="ताज्या बातम्या"), answer="संसदेत चर्चा सुरू आहे. https://x.test **ठीक**")
    res = make(core_http, llm).handle(uid, "आजच्या ताज्या बातम्या काय आहेत")
    assert brave == [("ताज्या बातम्या", "mr")]
    assert res.filler == "बघतो…"
    assert res.reply == "संसदेत चर्चा सुरू आहे. ठीक" and "http" not in res.reply and "*" not in res.reply
    assert res.intent == "CHAT" and res.source == "llm" and res.trace["web"] == "search"
    system, _ = llm.web_calls[0]
    assert "AT MOST TWO" in system and "संसदेत चर्चा सुरू आहे." in system and "https://e.test" not in system


@pytest.mark.parametrize("text", ["मला छातीत दुखतंय", "mala jagaychi iccha nahi"])
def test_safety_runs_first_and_never_searches(core_http, uid, brave, text):
    llm = Llm(_understand())
    res = make(core_http, llm).handle(uid, text)
    assert res.mode == "safety" and brave == [] and llm.calls == []


@pytest.mark.parametrize("text", ["बीपीची गोळी दोन घेऊ का", "शुगर वाढली तर काय करायचं", "can I double my dose today"])
def test_medicine_and_health_words_never_search(core_http, uid, brave, text):
    llm = Llm(_understand())
    res = make(core_http, llm).handle(uid, text)
    assert brave == [] and llm.web_calls == []
    assert res.reply != "" and "doctor" in res.reply.lower() or "डॉक्टर" in res.reply


def test_search_failure_gives_the_fixed_line(core_http, uid, monkeypatch):
    monkeypatch.setattr(web_search, "search", lambda *a, **k: None)
    res = make(core_http, Llm(_understand())).handle(uid, "आजच्या बातम्या सांग")
    assert res.reply == rp.R["mr"]["web_none"] == "आत्ता माहिती मिळाली नाही." and res.source == "rules"


def test_missing_key_gives_the_fixed_line_without_a_request(core_http, uid, monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY")
    res = make(core_http, Llm(_understand())).handle(uid, "आजच्या बातम्या सांग")
    assert res.reply == "आत्ता माहिती मिळाली नाही."


def test_llm_answer_failure_gives_the_fixed_line(core_http, uid, brave):
    res = make(core_http, Llm(_understand(), answer="")).handle(uid, "आजच्या बातम्या सांग")
    assert res.reply == "आत्ता माहिती मिळाली नाही."


def test_weather_uses_open_meteo_and_the_elders_city(core_http, uid, brave, monkeypatch):
    monkeypatch.setenv("ARJUN_CITY", "Pune")
    got = []
    monkeypatch.setattr(weather, "current_weather", lambda city, lang="mr", **k: got.append(city) or "ढगाळ आहे.")
    res = make(core_http, Llm(_understand())).handle(uid, "आज पाऊस पडेल का")
    assert got == ["Pune"] and brave == [] and res.reply == "ढगाळ आहे." and res.trace["web"] == "weather"


def test_weather_without_a_city_asks_instead_of_guessing(core_http, uid, brave, monkeypatch):
    monkeypatch.delenv("ARJUN_CITY", raising=False)
    monkeypatch.setattr(weather, "current_weather", lambda *a, **k: pytest.fail("no city, no lookup"))
    res = make(core_http, Llm(_understand())).handle(uid, "आज पाऊस पडेल का")
    assert res.reply == rp.R["mr"]["web_city"] and brave == []


# ---- the eval set ------------------------------------------------------------------------------------
def _cases():
    return [json.loads(line) for line in EVAL.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_eval_set_has_at_least_fifteen_turns():
    assert len(_cases()) >= 15


def test_web_eval_routing_latency_and_samples(core_http, uid, monkeypatch):
    """System result: every eval turn routes as expected with a mocked Brave/Open-Meteo/LLM. The latencies are the
    in-process cost of the pipeline only (all network mocked at zero delay); they say nothing about real Brave/LLM."""
    monkeypatch.setenv("ARJUN_CITY", "Pune")
    monkeypatch.setattr(weather, "current_weather", lambda city, lang="mr", **k: f"{city}: ढगाळ आहे.")
    rows, lat, correct = [], [], 0
    for case in _cases():
        searches = []
        snippets = case.get("snippets")

        def fake(query, lang="mr", _s=searches, _sn=snippets, **kw):
            _s.append(query)
            return _sn

        monkeypatch.setattr(web_search, "search", fake)
        llm = Llm(_understand(web=case["web"], query=case.get("q", "")), answer=case.get("answer", ""))
        eng = make(core_http, llm)
        t = time.perf_counter()
        res = eng.handle(uid, case["text"])
        lat.append((time.perf_counter() - t) * 1000)
        how = res.trace.get("web")
        expect = case["expect"]
        ok = {
            "weather": how == "weather" and not searches,
            "search": how == "search" and len(searches) == 1 and res.reply == case["answer"] and res.filler,
            "search_fail": how == "search_failed" and res.reply == "आत्ता माहिती मिळाली नाही.",
            "blocked": not searches and not res.filler and bool(res.reply),
            "safety": res.mode == "safety" and not searches and not llm.calls,
            "no_web": how is None and not searches and not res.filler,
        }[expect]
        rows.append((case["id"], expect, bool(ok), res.reply))
        correct += bool(ok)
    bad = [r for r in rows if not r[2]]
    assert not bad, bad
    lat.sort()
    out = os.environ.get("WEB_EVAL_REPORT")
    if out:
        Path(out).write_text(json.dumps({
            "turns": len(rows), "routed_ok": correct, "p50_ms": round(statistics.median(lat), 1),
            "p95_ms": round(lat[min(len(lat) - 1, int(len(lat) * 0.95))], 1),
            "samples": [{"id": r[0], "reply": r[3]} for r in rows],
        }, ensure_ascii=False, indent=1), encoding="utf-8")
