"""LLM provider settings: LLM_* names, EVON_* kept as aliases (T9 follow-up: hosted LLM for open talk)."""

import json
import logging

import httpx
from fastapi.testclient import TestClient
from reasoning_svc import config
from reasoning_svc.evon import EvonClient, load_intent_schema

HOSTED = {
    "LLM_BASE_URL": "https://api.example.test/v1",
    "LLM_MODEL": "example-small",
    "LLM_API_KEY": "sk-secret-123",
    "LLM_PROVIDER_NAME": "ExampleAI",
}


def test_llm_names_configure_a_hosted_provider():
    s = config.llm_settings(HOSTED)
    assert (s.base_url, s.model, s.api_key, s.provider) == (
        "https://api.example.test/v1", "example-small", "sk-secret-123", "ExampleAI",
    )
    assert s.configured


def test_evon_names_still_work_as_aliases():
    s = config.llm_settings(
        {"EVON_BASE_URL": "http://evon:8000/v1", "EVON_MODEL": "gnani/evon", "EVON_API_KEY": "k"}
    )
    assert (s.base_url, s.model, s.api_key) == ("http://evon:8000/v1", "gnani/evon", "k")
    assert s.provider == "evon" and s.configured


def test_new_names_win_and_never_borrow_the_evon_model_name():
    # an Evon model name sent to a hosted provider would just 404; a missing LLM_MODEL means "not configured"
    s = config.llm_settings({"LLM_BASE_URL": "https://x.test/v1", "EVON_MODEL": "gnani/evon", "EVON_API_KEY": "old"})
    assert s.model == "" and s.api_key == "" and not s.configured


def test_nothing_set_means_no_llm():
    s = config.llm_settings({})
    assert not s.configured and s.base_url == ""


def test_template_kwargs_flag_for_non_vllm_providers():
    assert config.llm_settings({"EVON_BASE_URL": "u", "EVON_MODEL": "m"}).send_template_kwargs is True
    assert config.llm_settings({"EVON_BASE_URL": "u", "EVON_SEND_TEMPLATE_KWARGS": "0"}).send_template_kwargs is False
    both = {**HOSTED, "EVON_SEND_TEMPLATE_KWARGS": "1", "LLM_SEND_TEMPLATE_KWARGS": "0"}
    assert config.llm_settings(both).send_template_kwargs is False


def test_limits_have_the_agreed_defaults_and_ignore_nonsense():
    s = config.llm_settings(HOSTED)
    assert (s.timeout_s, s.max_tokens, s.history_exchanges) == (4.0, 120, 4)
    t = config.llm_settings({**HOSTED, "LLM_TIMEOUT_S": "2.5", "LLM_MAX_TOKENS": "80"})
    assert (t.timeout_s, t.max_tokens) == (2.5, 80)
    bad = config.llm_settings({**HOSTED, "LLM_TIMEOUT_S": "abc", "LLM_MAX_TOKENS": "-5"})
    assert (bad.timeout_s, bad.max_tokens) == (4.0, 120)


def test_the_key_never_shows_in_repr_or_health():
    s = config.llm_settings(HOSTED)
    assert "sk-secret-123" not in repr(s) and "sk-secret-123" not in str(s)
    from reasoning_svc.main import app

    body = TestClient(app).get("/health").json()
    assert {"status", "llm_configured", "llm_provider", "evon_configured"} <= set(body)
    assert "key" not in json.dumps(body).lower()


def _client(handler, **kw):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return EvonClient("https://api.example.test/v1", "example-small", http=http, schema=load_intent_schema(),
                      provider="ExampleAI", **kw)


def test_every_call_is_logged_with_provider_model_latency_and_tokens_but_no_text(caplog):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "छान, पुढे काय झालं?"}}],
            "usage": {"prompt_tokens": 91, "completion_tokens": 12},
        })

    caplog.set_level(logging.INFO, logger="arjun.llm")
    _client(handler).companion_reply("आज मी बागेत गेलो होतो ही माझी गुप्त गोष्ट आहे", "mr")
    (rec,) = [r for r in caplog.records if r.name == "arjun.llm"]
    data = json.loads(rec.getMessage())
    assert data["provider"] == "ExampleAI" and data["model"] == "example-small"
    assert data["purpose"] == "companion" and data["ok"] is True
    assert data["prompt_tokens"] == 91 and data["completion_tokens"] == 12 and data["latency_ms"] >= 0
    assert "गुप्त" not in rec.getMessage() and "छान" not in rec.getMessage()  # no transcript, no reply text


def test_a_failed_call_is_logged_too_without_text(caplog):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="overloaded")

    caplog.set_level(logging.INFO, logger="arjun.llm")
    assert _client(handler).companion_reply("नमस्कार", "mr") is None
    data = json.loads([r for r in caplog.records if r.name == "arjun.llm"][0].getMessage())
    assert data["ok"] is False and data["error"] == "HTTPStatusError"


def test_limits_go_into_the_request():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((json.loads(req.content), req.extensions.get("timeout")))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ठीक आहे"}}]})

    c = _client(handler, max_tokens=90)
    c.companion_reply("नमस्कार", "mr", timeout=2.0)
    body, timeout = seen[0]
    assert body["max_tokens"] == 90 and body["temperature"] == config.COMPANION_TEMPERATURE
    assert timeout["read"] == 2.0


def test_running_token_totals_are_kept_for_the_compare_script():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "ठीक आहे"}}],
                                         "usage": {"prompt_tokens": 50, "completion_tokens": 7}})

    c = _client(handler)
    c.companion_reply("नमस्कार", "mr")
    c.companion_reply("नमस्कार", "mr")
    assert c.usage == {"calls": 2, "prompt_tokens": 100, "completion_tokens": 14}
