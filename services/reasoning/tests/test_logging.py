"""Logging (task F): under uvicorn the INFO loggers were never configured, so no "arjun.llm" line ever appeared. Each
provider call now logs ONE JSON line: provider, model, purpose, latency_ms, tokens, ok / error. Never the text, never the key."""

import json
import logging

import httpx
from reasoning_svc.evon import EvonClient, load_intent_schema
from reasoning_svc.main import configure_logging


def _client(handler, key="sk-THE-SECRET-KEY"):
    return EvonClient(
        "https://llm.test/v1", "sarvam-105b", http=httpx.Client(transport=httpx.MockTransport(handler)),
        schema=load_intent_schema(), provider="sarvam", api_key=key,
    )


def _ok(req):
    body = {"choices": [{"message": {"content": "छान. मग काय झालं?"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 210, "completion_tokens": 26}}
    return httpx.Response(200, json=body)


def test_configure_logging_turns_on_info_for_our_loggers_and_leaves_uvicorn_alone():
    uv = logging.getLogger("uvicorn")
    before = (uv.level, list(uv.handlers), uv.propagate)
    configure_logging()
    for name in ("arjun.llm", "reasoning.turn", "reasoning.wellbeing"):
        assert logging.getLogger(name).getEffectiveLevel() == logging.INFO
    assert (uv.level, list(uv.handlers), uv.propagate) == before


def test_configure_logging_is_idempotent():
    configure_logging()
    n = len(logging.getLogger("arjun").handlers)
    configure_logging()
    assert len(logging.getLogger("arjun").handlers) == n


def test_a_successful_call_logs_one_json_line_with_the_numbers(caplog):
    configure_logging()
    with caplog.at_level(logging.INFO, logger="arjun.llm"):
        reply = _client(_ok).companion_reply("आज मी बागेत गेले होते", "mr")
    assert reply
    lines = [json.loads(r.getMessage()) for r in caplog.records if r.name == "arjun.llm"]
    assert len(lines) == 1
    rec = lines[0]
    assert (rec["provider"], rec["model"], rec["purpose"], rec["ok"]) == ("sarvam", "sarvam-105b", "companion", True)
    assert (rec["prompt_tokens"], rec["completion_tokens"], rec["finish_reason"]) == (210, 26, "stop")
    assert isinstance(rec["latency_ms"], int)


def test_a_failed_call_logs_the_error_type_only(caplog):
    def boom(req):
        return httpx.Response(500, json={"error": "upstream said: the elder's words were X"})

    configure_logging()
    with caplog.at_level(logging.INFO, logger="arjun.llm"):
        assert _client(boom).companion_reply("आज मी बागेत गेले होते", "mr") is None
    rec = json.loads([r.getMessage() for r in caplog.records if r.name == "arjun.llm"][0])
    assert rec["ok"] is False and rec["error"] == "HTTPStatusError" and "latency_ms" in rec


def test_no_log_line_ever_holds_the_text_or_the_key(caplog):
    configure_logging()
    said = "माझं डोकं दुखतं आहे"
    with caplog.at_level(logging.DEBUG):
        _client(_ok).companion_reply(said, "mr")
        _client(_ok).extract_intent(said, "mr", __import__("datetime").datetime(2026, 10, 31, 9, 0), "07:00", "13:00", "20:00")
    everything = "\n".join(r.getMessage() for r in caplog.records)
    assert "sk-THE-SECRET-KEY" not in everything and said not in everything and "छान. मग काय झालं?" not in everything
