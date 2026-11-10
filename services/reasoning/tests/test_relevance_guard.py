"""Relevance guard (2026-11-10): a companion reply must be ABOUT what she just said. Cheap overlap first, a small LLM yes/no only when the
overlap is low, ONE retry ("answer exactly: her sentence"), then a short question that quotes HER words. LLM mocked."""

import json

import httpx
import pytest
from reasoning_svc import config, relevance
from reasoning_svc.core_client import CoreClient
from reasoning_svc.evon import EvonClient, load_intent_schema
from reasoning_svc.turn import TurnEngine
from test_web_search import NOW, _understand

HER = "माझा नातू आर्यन उद्या शाळेत स्पर्धेला जाणार आहे"
ON = "आर्यनची स्पर्धा उद्या आहे, त्याला शुभेच्छा."
OFF = "क्रिकेटचा सामना काल खूप रंगला होता."


@pytest.fixture(autouse=True)
def guard_on(monkeypatch):
    monkeypatch.setattr(config, "RELEVANCE_GUARD", True)


class Script:
    """understanding -> `first`; a relevance yes/no -> judged by `judge(reply)`; a companion retry -> the next of `retries`."""

    def __init__(self, first, retries=(), judge=lambda r: "no" if "क्रिकेट" in r or "शेअर" in r or r == "ठीक आहे." else "yes", self_check=None):
        self.first, self.retries, self.judge, self.self_check = first, list(retries), judge, self_check
        self.kinds: list[str] = []
        self.systems: list[str] = []

    def __call__(self, req):
        body = json.loads(req.content)
        system, last = body["messages"][0]["content"], body["messages"][-1]["content"]
        if "Return ONLY one JSON object" in system:
            self.kinds.append("understand")
            payload = {**_understand(web=False), "reply": self.first}
            if self.self_check is not None:
                payload["relevance_self_check"] = self.self_check
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]})
        if system.startswith("You judge ONE"):
            self.kinds.append("relevance")
            reply = last.split("REPLY:", 1)[1].strip()
            return httpx.Response(200, json={"choices": [{"message": {"content": self.judge(reply)}}]})
        self.kinds.append("retry")
        self.systems.append(system)
        out = self.retries.pop(0) if self.retries else OFF
        return httpx.Response(200, json={"choices": [{"message": {"content": out}}]})


def engine(core_http, script):
    http = httpx.Client(transport=httpx.MockTransport(script))
    return TurnEngine(CoreClient(core_http), EvonClient("https://llm.test/v1", "m", http=http, schema=load_intent_schema(), provider="T"), clock=lambda: NOW, ask_first=False)


def test_an_on_topic_reply_passes_on_word_overlap_with_no_extra_llm_call(core_http, uid):
    s = Script(ON)
    eng = engine(core_http, s)
    res = eng.handle(uid, HER)
    assert res.reply == ON and s.kinds == ["understand"]
    assert eng.last_relevance[uid]["score"] >= relevance.PASS_SCORE and eng.last_relevance[uid]["retried"] == 0
    assert eng.relevance["cheap_pass"] == 1


def test_low_overlap_asks_the_model_and_a_yes_lets_it_through(core_http, uid):
    reply = "छान बातमी आहे ही."  # no shared words, but fine
    s = Script(reply)
    res = engine(core_http, s).handle(uid, HER)
    assert res.reply == reply and s.kinds == ["understand", "relevance"]


def test_an_off_topic_reply_is_retried_once_with_her_exact_sentence(core_http, uid):
    s = Script(OFF, retries=[ON])
    eng = engine(core_http, s)
    res = eng.handle(uid, HER)
    assert res.reply == ON and s.kinds == ["understand", "relevance", "retry"]
    assert "Answer exactly this sentence of hers" in s.systems[0] and HER in s.systems[0]
    assert eng.last_relevance[uid]["retried"] == 1 and eng.relevance["retried"] == 1 and eng.relevance["clarified"] == 0


def test_still_off_topic_after_the_retry_asks_a_question_quoting_her_words(core_http, uid):
    s = Script(OFF, retries=["शेअर बाजार आज वर गेला."])
    eng = engine(core_http, s)
    res = eng.handle(uid, HER)
    assert res.reply == relevance.clarify(HER, "mr") and "आर्यन" in res.reply and "स्पर्धेला" in res.reply
    assert res.reply.endswith("?") and not relevance.is_generic(res.reply)
    assert eng.last_relevance[uid]["clarified"] is True and eng.relevance["clarified"] == 1
    assert OFF not in res.reply and "क्रिकेट" not in res.reply  # the wandering reply is never spoken


def test_a_generic_filler_is_replaced_without_asking_the_model_first(core_http, uid):
    s = Script("ठीक आहे.", retries=[ON])
    res = engine(core_http, s).handle(uid, HER)
    assert res.reply == ON and s.kinds == ["understand", "retry"]  # no yes/no call: "ठीक आहे." is generic by rule


def test_the_model_doubting_its_own_answer_goes_straight_to_the_retry(core_http, uid):
    s = Script(OFF, retries=[ON], self_check=False)
    res = engine(core_http, s).handle(uid, HER)
    assert res.reply == ON and s.kinds == ["understand", "retry"]


def test_a_self_check_false_does_not_override_a_reply_that_plainly_uses_her_words(core_http, uid):
    s = Script(ON, self_check=False)
    assert engine(core_http, s).handle(uid, HER).reply == ON and s.kinds == ["understand"]


def test_a_short_answer_is_scored_against_the_open_question(core_http, uid):
    s = Script("ठीक, मग भजन लावतो.")
    eng = engine(core_http, s)
    eng.memory.arjun_said(uid, NOW, "आज भजन लावू का?", "checkin")
    res = eng.handle(uid, "तेच")
    assert "भजन" in res.reply and "relevance" not in s.kinds  # the reply picks up the question's word: cheap pass


def test_no_llm_budget_or_a_dead_judge_never_blocks_a_reply(core_http, uid):
    class Mute(Script):
        def __call__(self, req):
            if json.loads(req.content)["messages"][0]["content"].startswith("You judge ONE"):
                return httpx.Response(500, json={})
            return super().__call__(req)

    reply = "छान बातमी आहे ही."
    assert engine(core_http, Mute(reply)).handle(uid, HER).reply == reply


def test_the_switch_turns_the_guard_off(core_http, uid, monkeypatch):
    monkeypatch.setattr(config, "RELEVANCE_GUARD", False)
    s = Script(OFF)
    assert engine(core_http, s).handle(uid, HER).reply == OFF and s.kinds == ["understand"]


def test_the_log_line_carries_score_and_retry_but_never_her_words(core_http, uid, caplog):
    caplog.set_level("INFO", logger="reasoning.turn")
    engine(core_http, Script(OFF, retries=[ON])).handle(uid, HER)
    lines = [r.message for r in caplog.records if "relevance_score" in r.message]
    assert lines and json.loads(lines[-1])["retried"] == 1 and "आर्यन" not in lines[-1] and "क्रिकेट" not in lines[-1]


# ---- the pure helpers --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("lang", ["mr", "hi", "en", "bn", "gu", "kn", "ml", "pa", "ta", "te"])
def test_the_clarifying_question_quotes_her_words_in_every_language(lang):
    q = relevance.clarify("माझा नातू आर्यन उद्या शाळेत जाणार आहे", lang)
    assert "आर्यन" in q and "?" in q and "{q}" not in q


def test_generic_detection_and_scores():
    for g in ("ठीक आहे.", "सांगा ना", "okay", "I'm listening.", "मी ऐकतोय"):
        assert relevance.is_generic(g), g
    assert not relevance.is_generic("आर्यनला शुभेच्छा.")
    assert relevance.score(HER, ON) >= relevance.PASS_SCORE > relevance.score(HER, OFF)
    assert relevance.score("हो", "ठीक आहे", pending="भजन लावू का?") == 0.0 and relevance.score("हो", "भजन लावतो", pending="भजन लावू का?") > 0.2


def test_relevance_check_parses_yes_no_and_unknown():
    def client(answer):
        h = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": answer}}]})))
        return EvonClient("https://llm.test/v1", "m", http=h, schema=load_intent_schema(), provider="T")

    assert client("Yes.").relevance_check("a", "b") is True
    assert client("no").relevance_check("a", "b") is False
    assert client("maybe").relevance_check("a", "b") is None
