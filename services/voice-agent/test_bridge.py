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
    assert r.mode == "fallback" and r.text and "समजलं नाही" not in r.text


def test_fallback_on_network_error():
    def down(request):
        raise httpx.ConnectError("reasoning down", request=request)

    r = reply_or_fallback(1, "x", "mr-IN", _client(down))
    assert r.mode == "fallback" and r.text and "समजलं नाही" not in r.text


def test_fallback_on_timeout():
    def slow(request):
        raise httpx.ReadTimeout("too slow", request=request)

    assert reply_or_fallback(1, "x", "hi-IN", _client(slow)).text.startswith("क्या आप")


def test_fallback_on_malformed_json():
    r = reply_or_fallback(1, "x", "en-IN", _client(lambda req: httpx.Response(200, json={"oops": 1})))
    assert r.mode == "fallback" and r.text.startswith("Are you asking")


def test_unknown_language_uses_specific_transcript_language_or_english_fallback():
    assert fallback_text("en-IN,hi-IN", "Hello") == "Are you asking about Hello?"
    assert fallback_text("ta-IN", "food").startswith("நீங்கள்")


def test_reasoning_outage_names_the_requested_topic_and_never_uses_generic_fallback():
    down = _client(lambda req: httpx.Response(502, json={}))
    result = reply_or_fallback(1, "YouTube pe bhajan chalao", "hi-IN", down)
    assert result.mode == "fallback" and "गाना" in result.text and "समझ नहीं आया" not in result.text


def test_reasoning_outage_keeps_local_distress_path_in_safety_mode():
    down = _client(lambda req: httpx.Response(502, json={}))
    result = reply_or_fallback(1, "I want to die", "en-IN", down)
    assert result.mode == "safety" and "family" in result.text and not result.silent


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


def test_prepare_reasoning_returns_the_json_and_never_raises():
    import httpx
    from bridge import prepare_reasoning

    seen = []

    def ok(req):
        seen.append((req.url.path, req.extensions["timeout"]["read"]))
        return httpx.Response(200, json={"needs_web": True, "filler": "बघतो…", "hold": "x"})

    assert prepare_reasoning(1, "आज पाऊस", "mr", httpx.Client(transport=httpx.MockTransport(ok)))["needs_web"] is True
    assert seen == [("/turn/prepare", 0.3)]
    for handler in (lambda r: httpx.Response(500), lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow"))):
        assert prepare_reasoning(1, "x", "mr", httpx.Client(transport=httpx.MockTransport(handler))) is None
