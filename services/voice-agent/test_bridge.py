import json

import httpx
from bridge import ask_reasoning, fallback_text, reply_or_fallback, report_sound_event


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ask_reasoning_parses_reply():
    def ok(request):
        assert request.url.path == "/turn"
        return httpx.Response(200, json={"reply": "ठीक आहे", "mode": "care", "awaiting_confirmation": True})

    r = ask_reasoning(1, "aaj kay aahe", _client(ok))
    assert r.text == "ठीक आहे" and r.mode == "care" and r.awaiting_confirmation


def test_fallback_on_server_error():
    r = reply_or_fallback(1, "x", "mr-IN", _client(lambda req: httpx.Response(502, json={})))
    assert r.mode == "fallback" and r.text == fallback_text("mr")


def test_fallback_on_network_error():
    def down(request):
        raise httpx.ConnectError("reasoning down", request=request)

    r = reply_or_fallback(1, "x", "mr-IN", _client(down))
    assert r.mode == "fallback" and "पुन्हा" in r.text


def test_fallback_on_timeout():
    def slow(request):
        raise httpx.ReadTimeout("too slow", request=request)

    assert reply_or_fallback(1, "x", "hi-IN", _client(slow)).text == fallback_text("hi")


def test_fallback_on_malformed_json():
    r = reply_or_fallback(1, "x", "en-IN", _client(lambda req: httpx.Response(200, json={"oops": 1})))
    assert r.mode == "fallback" and r.text == fallback_text("en")


def test_unknown_language_falls_back_to_marathi():
    assert fallback_text("en-IN,hi-IN") == fallback_text("en")
    assert fallback_text("ta-IN") == fallback_text("mr")


def test_detected_language_code_is_forwarded_without_transcript_logging():
    def ok(request):
        assert json.loads(request.read()) == {"user_id": 1, "text": "hello", "language_code": "ta-IN"}
        return httpx.Response(200, json={"reply": "வணக்கம்", "mode": "care", "awaiting_confirmation": False})

    assert ask_reasoning(1, "hello", _client(ok), "ta-IN").text == "வணக்கம்"


def test_sound_event_forwards_label_and_score_only():
    def ok(request):
        assert request.url.path == "/sound-event"
        assert json.loads(request.read()) == {"user_id": 1, "label": "cough", "confidence": 0.8}
        return httpx.Response(200, json={"recorded": True})

    assert report_sound_event(1, "cough", 0.8, http=_client(ok))
