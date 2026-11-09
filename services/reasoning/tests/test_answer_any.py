"""Answer ANY question (2026-11-09): the answer router (know / search / tool / refuse_safe), the query builder, Tavily's
advanced request, the synthesis prompt, follow-ups, the quality gate and the safety-first guarantees.
Every provider (LLM, Tavily, Open-Meteo) is mocked."""

import json
from datetime import date, timedelta

import httpx
import pytest
from reasoning_svc import qa
from reasoning_svc import replies as rp
from reasoning_svc import turn as turn_mod
from reasoning_svc.tools import weather, web_search
from test_web_search import Llm, _understand, client, make

TODAY = date(2026, 11, 9)


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    web_search.reset()
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-test-key-123456")
    yield
    web_search.reset()


def route(mode, *, reply="", know=None, ts=False, query="", queries=None, entity=""):
    base = _understand(web=False)
    base.update(reply=reply, answer_mode=mode, know_confidence=know if know is not None else (0.97 if mode == "know" else 0.0),
                time_sensitive=ts, query_en=query, queries=queries, entity=entity, needs_web=None, web_query=None)
    return base


LONG = "Details about this are written here in full so the result is not thin. " * 3


@pytest.fixture()
def tav(monkeypatch):
    """A fake Tavily: records every call; `.reply` is what it returns (a dict in full mode)."""
    class T:
        calls: list = []
        reply = {"answer": "", "results": [{"title": "Top", "snippet": LONG, "source_domain": "bbc.com", "score": 0.9, "age_days": 1}]}

    T.calls = []

    def fake(query, lang="mr", **kw):
        T.calls.append((query, kw))
        return T.reply

    monkeypatch.setattr(web_search, "search", fake)
    return T


# ---- 1. the router ----------------------------------------------------------------------------------------------
def test_know_answers_from_the_llm_with_no_search(core_http, uid, tav):
    res = make(core_http, Llm(route("know", reply="पाण्याचं सूत्र एच टू ओ आहे."))).handle(uid, "पाण्याचं सूत्र काय")
    assert res.reply == "पाण्याचं सूत्र एच टू ओ आहे." and tav.calls == [] and not res.filler


def test_know_with_low_confidence_is_searched_instead(core_http, uid, tav):
    llm = Llm(route("know", reply="कदाचित ५", know=0.6, query="how many moons does Saturn have"), answer="शनीला १४६ चंद्र आहेत.")
    res = make(core_http, llm).handle(uid, "शनीला किती चंद्र आहेत")
    assert len(tav.calls) == 1 and res.trace["web"] == "search" and res.reply == "शनीला १४६ चंद्र आहेत."
    assert "कदाचित ५" in llm.web_calls[0][0]  # the model's own draft goes to the synthesis step as an unverified hint


def test_a_time_sensitive_know_is_searched(core_http, uid, tav):
    llm = Llm(route("know", reply="x", know=0.99, ts=True, query="current prime minister of India"), answer="नरेंद्र मोदी.")
    make(core_http, llm).handle(uid, "देशाचे पंतप्रधान कोण")
    assert len(tav.calls) == 1


def test_a_missing_mode_with_the_old_needs_web_flag_still_searches(core_http, uid, tav):
    make(core_http, Llm(_understand(query="india score"), answer="भारत ३ धावांनी जिंकला.")).handle(uid, "भारताचा स्कोर काय")
    assert len(tav.calls) == 1


def test_refuse_safe_is_the_fixed_ask_your_doctor_line_and_never_searches(core_http, uid, tav):
    res = make(core_http, Llm(route("refuse_safe"))).handle(uid, "या गोष्टीसाठी किती घ्यावं सांगा")
    assert res.reply == rp.R["mr"]["web_health"] and tav.calls == [] and res.trace["web"] == "blocked"


def test_tool_mode_is_the_weather_tool_not_tavily(core_http, uid, tav, monkeypatch):
    monkeypatch.setenv("ARJUN_CITY", "Pune")
    monkeypatch.setattr(weather, "current_weather", lambda city, lang="mr", **k: "ढगाळ आहे.")
    res = make(core_http, Llm(route("tool"))).handle(uid, "बाहेर कसं आहे")
    assert res.reply == "ढगाळ आहे." and tav.calls == []


# ---- 2. the query builder -------------------------------------------------------------------------------------
def test_builder_adds_todays_date_to_time_sensitive_queries_and_caps_at_two():
    llm = {"queries": ["India vs Australia score", "Pune weather", "third one"], "web_query": "ignored"}
    out = qa.build_queries(llm, "x", TODAY, True)
    assert out == ["India vs Australia score 9 November 2026", "Pune weather 9 November 2026"]
    assert qa.build_queries({"web_query": "Saturn moons"}, "x", TODAY, False) == ["Saturn moons"]
    assert qa.build_queries({"web_query": "match 2025 final"}, "x", TODAY, True) == ["match 2025 final"]  # has a year already
    assert qa.build_queries({}, "  her   own words ", TODAY, False) == ["her own words"]


def test_a_compound_question_runs_two_queries_and_merges_the_results(core_http, uid, tav):
    tav.reply = {"answer": "", "results": [{"title": "A", "snippet": LONG, "source_domain": "x.com", "score": 0.9, "age_days": 1}]}
    llm = Llm(route("search", queries=["Virat Kohli age", "Virat Kohli wife"], entity="Virat Kohli"), answer="३७ वर्षांचे; पत्नी अनुष्का.")
    make(core_http, llm).handle(uid, "विराटचं वय आणि बायको कोण")
    assert [c[0] for c in tav.calls] == ["Virat Kohli age", "Virat Kohli wife"]


def test_weak_results_get_exactly_one_reworded_retry(core_http, uid, tav):
    tav.reply = {"answer": "", "results": [{"title": "Thin", "snippet": "short", "source_domain": "x.com", "score": 0.9, "age_days": 1}]}
    make(core_http, Llm(route("search", query="obscure thing", entity="Gopal"), answer="काहीतरी आहे.")).handle(uid, "गोपाल बद्दल सांगा")
    assert len(tav.calls) == 2 and tav.calls[0][0] != tav.calls[1][0]
    assert "गोपाल बद्दल सांगा" in tav.calls[1][0]  # her own words, with the entity in front


# ---- 3. Tavily ---------------------------------------------------------------------------------------------------
def test_full_mode_posts_advanced_five_results_and_a_basic_answer():
    seen = []

    def h(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"answer": "Short.", "results": []})

    web_search.search("q", "en", client=client(h), sleep=lambda s: None, full=True)
    assert seen[0] == {"query": "q", "max_results": 5, "search_depth": "advanced", "include_answer": "basic", "topic": "general"}


def test_news_topic_gets_a_time_range_and_domains_are_still_enforced():
    seen = []

    def h(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"results": [{"title": "T", "content": "d", "url": "https://x.example/a", "score": 0.9}]})

    out = web_search.search("india news", "en", client=client(h), sleep=lambda s: None, full=True, news=True, domains=["lokmat.com"])
    assert seen[0]["topic"] == "news" and seen[0]["time_range"] == "week" and seen[0]["include_domains"] == ["lokmat.com"]
    assert out is None  # x.example is not an approved domain: dropped


def test_low_score_and_stale_results_are_dropped_and_age_is_computed_in_code():
    old = (TODAY - timedelta(days=90)).isoformat()
    new = (TODAY - timedelta(days=2)).isoformat()
    body = {"answer": "A.", "results": [
        {"title": "low", "content": "x", "url": "https://a.test/1", "score": 0.3, "published_date": new},
        {"title": "stale", "content": "x", "url": "https://a.test/2", "score": 0.9, "published_date": old},
        {"title": "good", "content": "x", "url": "https://a.test/3", "score": 0.8, "published_date": new},
        {"title": "undated", "content": "x", "url": "https://a.test/4", "score": 0.7},
    ]}
    out = web_search.search("q", "en", client=client(lambda r: httpx.Response(200, json=body)), sleep=lambda s: None,
                            full=True, max_age_days=14, today=TODAY)
    assert [x["title"] for x in out["results"]] == ["good", "undated"]
    assert out["results"][0]["age_days"] == 2 and out["results"][1]["age_days"] is None and out["answer"] == "A."


def test_ages_come_from_a_birth_date_and_todays_date_not_from_article_text():
    facts = qa.computed_facts(["Narendra Modi (born 17 September 1950) is aged 71 in this old article."], TODAY)
    assert "76 years" in facts and "71" not in facts.split("age is")[1]
    assert qa.computed_facts(["The actor was born on March 3, 1990."], TODAY).count("36 years") == 1
    assert qa.computed_facts(["no dates here"], TODAY) == ""


# ---- 4. the synthesis prompt --------------------------------------------------------------------------------------
def test_synthesis_gets_todays_date_the_engine_answer_sources_and_the_ambiguity_rule(core_http, uid, tav):
    tav.reply = {"answer": "The engine says 42.", "results": [{"title": "T", "snippet": LONG, "source_domain": "espncricinfo.com", "score": 0.9, "age_days": 1}]}
    llm = Llm(route("search", query="runs", entity="Rohit"), answer="४२ धावा.")
    make(core_http, llm).handle(uid, "रोहितने किती धावा केल्या")
    system = llm.web_calls[0][0]
    for needle in ("9 November 2026", "The engine says 42.", "ESPNcricinfo", "ONE short clarifying question", "AT MOST TWO",
                   "the specific fact first", "NEVER invent", "sources disagree", "Rohit"):
        assert needle in system, needle


def test_an_ambiguity_question_is_accepted_as_an_answer(core_http, uid, tav):
    llm = Llm(route("search", query="Sachin"), answer="कोणता सचिन? तेंडुलकर, पायलट की वाझे?")
    res = make(core_http, llm).handle(uid, "सचिनचं वय किती")
    assert res.reply.endswith("?") and res.trace["web"] == "search" and len(llm.web_calls) == 1


# ---- 5. follow-ups and the tiny cache ---------------------------------------------------------------------------
def test_a_follow_up_sees_the_last_topic_and_it_expires(core_http, uid, tav):
    llm = Llm(route("search", query="Modi wife", entity="Narendra Modi"), answer="जशोदाबेन.")
    eng = make(core_http, llm)
    eng.handle(uid, "मोदींच्या पत्नी कोण")
    eng.handle(uid, "आणि त्यांचं वय?")
    understanding = [c[0] for c in llm.calls if "Return ONLY one JSON object" in c[0]]
    assert "she last asked" not in understanding[0]
    assert "she last asked" in understanding[1] and "Narendra Modi" in understanding[1]
    eng._topic[uid] = (*eng._topic[uid][:3], eng._mono() - 601)
    assert eng._topic_block(uid) == ""


def test_a_repeated_question_is_answered_from_the_cache_without_searching_again(core_http, uid, tav):
    eng = make(core_http, Llm(route("search", query="gold price"), answer="सोनं ७५ हजार रुपये आहे."))
    first = eng.handle(uid, "सोन्याचा भाव किती")
    second = eng.handle(uid, "सोन्याचा भाव किती")
    assert len(tav.calls) == 1 and first.reply == second.reply and second.trace["web"] == "cache"


# ---- 6. latency ------------------------------------------------------------------------------------------------
def test_the_web_turn_budget_is_six_seconds_and_the_hold_line_comes_at_four():
    assert turn_mod._WEB_TURN_BUDGET_S == 6.0
    from reasoning_svc.tools import web_search as ws

    assert ws.TIMEOUT_S <= 4.0


# ---- 7. the quality gate ----------------------------------------------------------------------------------------
def test_gate_checks_language_number_and_boilerplate():
    assert qa.answers_question("शनीला किती चंद्र", "शनीला १४६ चंद्र आहेत.", "mr") == (True, "")
    assert qa.answers_question("शनीला किती चंद्र", "शनीला खूप चंद्र आहेत.", "mr") == (False, "no_number")
    assert qa.answers_question("शनीला किती चंद्र", "Saturn has 146 moons.", "mr") == (False, "wrong_language")
    assert qa.answers_question("शनीला किती चंद्र", "ठीक आहे.", "mr")[0] is False
    assert qa.answers_question("how many moons", "Saturn has 146 moons.", "en") == (True, "")
    assert qa.answers_question("शनीला किती चंद्र", "मला पक्की खात्री नाही, ९ पेक्षा जास्त.", "mr")[0]
    assert qa.answers_question("எத்தனை", "சனிக்கு 146 நிலவுகள்.", "ta")[0]


def test_a_failing_draft_gets_one_stricter_retry_then_passes(core_http, uid, tav):
    class Seq(Llm):
        def __call__(self, req):
            body = json.loads(req.content)
            system = body["messages"][0]["content"]
            if "SEARCH RESULTS" in system:
                self.calls.append((system, ""))
                text = "Saturn has many moons." if "STRICT" not in system else "शनीला १४६ चंद्र आहेत."
                return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})
            return super().__call__(req)

    llm = Seq(route("search", query="saturn moons"))
    res = make(core_http, llm).handle(uid, "शनीला किती चंद्र आहेत")
    assert len(llm.web_calls) == 2 and "STRICT" in llm.web_calls[1][0]
    assert res.reply == "शनीला १४६ चंद्र आहेत." and res.trace["web"] == "search"


def test_two_failing_drafts_end_in_an_honest_not_sure_with_what_was_found(core_http, uid, tav):
    llm = Llm(route("search", query="saturn moons"), answer="Saturn has many moons.")
    res = make(core_http, llm).handle(uid, "शनीला किती चंद्र आहेत")
    assert len(llm.web_calls) == 2 and res.trace["web"] == "search_unsure"
    assert res.reply == rp.R["mr"]["web_unsure"].format(found="Top")


def test_no_result_at_all_is_the_fixed_no_information_line(core_http, uid, tav):
    tav.reply = None
    res = make(core_http, Llm(route("search", query="x"))).handle(uid, "काहीतरी विचित्र प्रश्न")
    assert res.reply == "आत्ता माहिती मिळाली नाही." and res.trace["web"] == "search_failed"


# ---- safety first ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["मला छातीत दुखतंय", "बीपीची गोळी दोन घेऊ का", "mala jagaychi iccha nahi"])
def test_emergency_distress_and_medicine_turns_never_reach_search(core_http, uid, tav, text):
    llm = Llm(route("search", query="anything"))
    res = make(core_http, llm).handle(uid, text)
    assert tav.calls == [] and llm.web_calls == [] and res.trace.get("web") != "search"


# ---- guards added after the first live eval (2026-11-09) ------------------------------------------------------------
def test_advanced_search_that_times_out_falls_back_to_basic_inside_the_same_deadline():
    seen = []

    def h(req):
        body = json.loads(req.content)
        seen.append(body["search_depth"])
        if body["search_depth"] == "advanced":
            raise httpx.ReadTimeout("slow", request=req)
        return httpx.Response(200, json={"answer": "A.", "results": [{"title": "T", "content": "d", "url": "https://a.test/1", "score": 0.9}]})

    out = web_search.search("q", "en", client=client(h), sleep=lambda s: None, full=True)
    assert seen == ["advanced", "basic"] and out["answer"] == "A."


def test_an_age_question_is_searched_even_when_the_model_is_sure(core_http, uid, tav):
    llm = Llm(route("know", reply="सचिन तेंडुलकरचं वय बावन्न वर्ष आहे.", know=0.99, entity="Sachin Tendulkar"), answer="५३ वर्षांचे.")
    res = make(core_http, llm).handle(uid, "सचिनचं वय किती")
    assert len(tav.calls) == 1 and res.reply == "५३ वर्षांचे."


def test_a_know_answer_in_the_wrong_language_is_searched_so_the_answer_is_written_in_hers(core_http, uid, tav):
    core_http.patch(f"/users/{uid}", json={"language": "en"})
    llm = Llm(route("know", reply="फ्रान्सची राजधानी पॅरिस आहे.", know=0.99, query="capital of France"), answer="Paris is the capital of France.")
    res = make(core_http, llm).handle(uid, "what is the capital of France")
    assert len(tav.calls) == 1 and res.reply == "Paris is the capital of France."


def test_ordinary_talk_is_never_turned_into_a_search(core_http, uid, tav):
    res = make(core_http, Llm(route("know", reply="छान, बागेत फिरणं चांगलं असतं.", know=0.99))).handle(uid, "सध्या मी रोज बागेत जातो")
    assert tav.calls == [] and res.reply == "छान, बागेत फिरणं चांगलं असतं."


def test_who_holds_an_office_is_always_searched_even_for_the_us_president(core_http, uid, tav):
    llm = Llm(route("know", reply="जो बायडन.", know=0.99), answer="डोनाल्ड ट्रम्प.")
    res = make(core_http, llm).handle(uid, "अमेरिकेचे राष्ट्राध्यक्ष कोण आहेत")
    assert len(tav.calls) == 1 and "ट्रम्प" in res.reply
