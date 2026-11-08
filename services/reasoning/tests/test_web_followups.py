"""Follow-ups to live web search: /turn/prepare, the elder's city, the 9 s time budget, the news-domain boundary.
The network is always mocked."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from reasoning_svc import main as reasoning_main
from reasoning_svc import replies as rp
from reasoning_svc import turn as turn_mod
from reasoning_svc.tools import weather, web_search
from test_web_search import Llm, _understand, client, make


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    web_search.reset()
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-test-key-123456")
    yield
    web_search.reset()


# ---- 1. /turn/prepare ----------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    ["आज पाऊस पडेल का", "आजच्या बातम्या सांगा", "भारताचा स्कोर काय आहे", "सोन्याचा भाव किती", "what is the weather today",
     "देशाचे पंतप्रधान कोण आहेत"],
)
def test_prepare_flags_live_fact_questions_with_a_filler(engine, text):
    out = engine.prepare(text)
    assert out["needs_web"] is True and out["filler"] and out["hold"]


@pytest.mark.parametrize(
    "text",
    ["मला छातीत दुखतंय", "बीपीची गोळी दोन घेऊ का", "mala jagaychi iccha nahi", "आज मी बागेत गेलो होतो", "नमस्कार"],
)
def test_prepare_never_flags_safety_health_or_ordinary_talk(engine, text):
    assert engine.prepare(text) == {**engine.prepare(text), "needs_web": False, "filler": ""}


def test_prepare_endpoint_is_rules_only_and_touches_nothing(core_http, monkeypatch):
    class NoCore:
        def __getattr__(self, name):
            raise AssertionError("prepare must not call core-api")

    eng = turn_mod.TurnEngine(NoCore(), None)  # type: ignore[arg-type]
    monkeypatch.setattr(reasoning_main, "_engine", eng)
    c = TestClient(reasoning_main.app)
    body = c.post("/turn/prepare", json={"user_id": 1, "text": "आज पाऊस पडेल का"}).json()
    assert body["needs_web"] is True and body["filler"] == "बघतो…"
    # /turn stays backward compatible: the old fields are all still there
    assert {"reply", "intent", "mode", "language", "awaiting_confirmation", "source", "trace"} <= set(reasoning_main.TurnOut.model_fields)


# ---- 2. city ---------------------------------------------------------------------------------------------
def _weather(monkeypatch):
    got = []
    monkeypatch.setattr(weather, "current_weather", lambda city, lang="mr", **k: got.append(city) or f"{city} ढगाळ.")
    return got


def test_profile_city_wins_over_env(core_http, uid, monkeypatch):
    core_http.patch(f"/users/{uid}", json={"city": "Nashik"})
    monkeypatch.setenv("ARJUN_CITY", "Pune")
    got = _weather(monkeypatch)
    make(core_http, Llm(_understand())).handle(uid, "आज पाऊस पडेल का")
    assert got == ["Nashik"]


def test_env_city_is_the_fallback(core_http, uid, monkeypatch):
    monkeypatch.setenv("ARJUN_CITY", "Pune")
    got = _weather(monkeypatch)
    make(core_http, Llm(_understand())).handle(uid, "आज पाऊस पडेल का")
    assert got == ["Pune"]


def test_no_city_asks_once_then_offers_to_save_and_saves_on_yes(core_http, uid, monkeypatch):
    monkeypatch.delenv("ARJUN_CITY", raising=False)
    got = _weather(monkeypatch)
    eng = make(core_http, Llm(_understand()))
    assert eng.handle(uid, "आज पाऊस पडेल का").reply == rp.R["mr"]["web_city"] and got == []
    answered = eng.handle(uid, "कोल्हापूर")
    assert got == ["कोल्हापूर"] and answered.reply.startswith("कोल्हापूर ढगाळ.") and answered.reply.endswith(rp.R["mr"]["web_city_offer"])
    assert core_http.get(f"/users/{uid}").json()["city"] is None  # offered, not yet saved
    assert eng.handle(uid, "हो").reply == rp.R["mr"]["web_city_saved"]
    assert core_http.get(f"/users/{uid}").json()["city"] == "कोल्हापूर"


def test_declining_the_offer_saves_nothing(core_http, uid, monkeypatch):
    monkeypatch.delenv("ARJUN_CITY", raising=False)
    _weather(monkeypatch)
    eng = make(core_http, Llm(_understand()))
    eng.handle(uid, "आज पाऊस पडेल का")
    eng.handle(uid, "कोल्हापूर")
    assert eng.handle(uid, "नको").reply == rp.R["mr"]["web_city_declined"]
    assert core_http.get(f"/users/{uid}").json()["city"] is None


def test_a_long_sentence_after_the_city_question_is_not_taken_as_a_city(core_http, uid, monkeypatch):
    monkeypatch.delenv("ARJUN_CITY", raising=False)
    got = _weather(monkeypatch)
    eng = make(core_http, Llm(_understand(web=False)))
    eng.handle(uid, "आज पाऊस पडेल का")
    eng.handle(uid, "आज मी बागेत फिरायला गेलो होतो खूप छान वाटलं")
    assert got == []


# ---- 3. time budget ---------------------------------------------------------------------------------------
def test_search_is_capped_at_four_seconds_and_the_turn_fits_under_the_nine_second_wait():
    assert web_search.TIMEOUT_S <= 4.0
    assert turn_mod._WEB_TURN_BUDGET_S < 9.0


def test_the_search_timeout_handed_to_tavily_never_exceeds_four_seconds(core_http, uid, monkeypatch):
    seen = []
    monkeypatch.setattr(web_search, "search", lambda q, lang="mr", **kw: seen.append(kw.get("timeout_s")))
    make(core_http, Llm(_understand())).handle(uid, "आजचा सामना कोण जिंकला")
    assert seen and all(0 < t <= 4.0 for t in seen)


# ---- 4. news only from the family's domains ---------------------------------------------------------------
def _raw(*urls):
    return [{"title": f"T{i}", "content": f"d{i}", "url": u} for i, u in enumerate(urls)]


def _patch_tavily(monkeypatch, raw):
    real = web_search.search
    asked = []

    def fake(query, lang="mr", **kw):
        asked.append((query, kw.get("domains")))
        return real(query, lang, client=client(lambda r: httpx.Response(200, json={"results": raw})), sleep=lambda s: None, **kw)

    monkeypatch.setattr(web_search, "search", fake)
    return asked


def _links(core_http, uid, *pairs):
    for label, url in pairs:
        core_http.post(f"/users/{uid}/app-links", json={"kind": "rss", "label": label, "value": url, "allow_other_host": True})


def test_news_uses_only_family_domains_drops_the_rest_and_names_the_source(core_http, uid, monkeypatch):
    _links(core_http, uid, ("लोकमत", "https://www.lokmat.com/rss"))
    asked = _patch_tavily(monkeypatch, _raw("https://evil.example/a", "https://m.lokmat.com/b"))
    llm = Llm(_understand(query="बातम्या"), answer="चर्चा सुरू आहे.")
    res = make(core_http, llm).handle(uid, "आजच्या बातम्या सांगा")
    assert asked[0][1] == ["lokmat.com"]  # Tavily is asked for that site only ...
    assert res.reply == "लोकमत नुसार: चर्चा सुरू आहे."  # ... and the family's own label is spoken
    system = llm.web_calls[0][0]
    assert "d1" in system and "d0" not in system and "evil.example" not in system  # the unapproved one never reaches the LLM


def test_news_with_only_unapproved_results_says_no_information(core_http, uid, monkeypatch):
    _links(core_http, uid, ("लोकमत", "https://lokmat.com/rss"))
    _patch_tavily(monkeypatch, _raw("https://evil.example/a", "https://lokmat.com.evil.example/b"))  # look-alike host
    llm = Llm(_understand(query="बातम्या"))
    res = make(core_http, llm).handle(uid, "आजच्या बातम्या सांगा")
    assert res.reply == "आत्ता माहिती मिळाली नाही." and llm.web_calls == []


def test_news_without_any_family_source_does_not_search(core_http, uid, monkeypatch):
    asked = _patch_tavily(monkeypatch, _raw("https://anything.example/a"))
    res = make(core_http, Llm(_understand(query="बातम्या"))).handle(uid, "आजच्या बातम्या सांगा")
    assert res.reply == "आत्ता माहिती मिळाली नाही." and asked == []


def test_non_news_may_use_any_result_and_names_no_source(core_http, uid, monkeypatch):
    _links(core_http, uid, ("लोकमत", "https://lokmat.com/rss"))
    asked = _patch_tavily(monkeypatch, _raw("https://anything.example/score"))
    res = make(core_http, Llm(_understand(query="सामना"), answer="भारत जिंकला.")).handle(uid, "आजचा सामना कोण जिंकला")
    assert asked[0][1] is None and res.reply == "भारत जिंकला." and "नुसार" not in res.reply


def test_tool_sends_news_topic_with_include_domains_and_postfilters():
    web_search.reset()
    seen = []

    def h(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"results": _raw("https://x.example/1", "https://a.b.lokmat.com/2")})

    out = web_search.search("बातम्या", "mr", client=client(h), sleep=lambda s: None, domains=["lokmat.com"])
    assert seen[0]["topic"] == "news" and seen[0]["include_domains"] == ["lokmat.com"]
    assert out == [{"title": "T1", "snippet": "d1", "source_domain": "a.b.lokmat.com"}]  # the unapproved one is dropped
