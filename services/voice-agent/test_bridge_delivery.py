import json

import httpx
from bridge import claim_next_delivery, mark_delivery_spoken, release_delivery, session_busy
from screenstate import attributes_for, closed_attributes, delivery_attributes
from turnlog import TurnLog

ITEM = {"delivery_id": 7, "kind": "medicine", "text": "औषधाची वेळ. X. Y. वेळ सकाळी 9:00 वाजता. घेतली का?",
        "screen": "medicine", "item": "dose:4", "awaiting_confirmation": True, "language": "mr"}


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_claim_next_posts_user_and_session_and_returns_the_item():
    seen = {}

    def handler(req):
        seen["path"], seen["body"] = req.url.path, json.loads(req.content)
        return httpx.Response(200, json=ITEM)

    assert claim_next_delivery(1, "job-9", _client(handler)) == ITEM
    assert seen == {
        "path": "/delivery/next",
        "body": {"user_id": 1, "session": "job-9", "media_playing": False},
    }


def test_claim_next_tells_reasoning_when_media_is_playing():
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=None)

    assert claim_next_delivery(1, "s", _client(handler), media_playing=True) is None
    assert seen["body"]["media_playing"] is True  # a check-in question is then postponed, a reminder is not


def test_claim_next_with_nothing_waiting_is_none():
    assert claim_next_delivery(1, "s", _client(lambda r: httpx.Response(200, json=None))) is None


def test_claim_next_never_raises_when_reasoning_is_down():
    def down(req):
        raise httpx.ConnectError("down", request=req)

    assert claim_next_delivery(1, "s", _client(down)) is None
    assert claim_next_delivery(1, "s", _client(lambda r: httpx.Response(502))) is None


def test_spoken_and_release_post_to_the_right_places():
    calls = []

    def handler(req):
        calls.append((req.url.path, json.loads(req.content)))
        return httpx.Response(204)

    http = _client(handler)
    mark_delivery_spoken(1, 7, "s", http)
    release_delivery(1, 7, "s", "tts", http)
    assert calls == [
        ("/delivery/7/spoken", {"user_id": 1, "session": "s"}),
        ("/delivery/7/release", {"user_id": 1, "session": "s", "reason": "tts"}),
    ]


def test_session_busy_returns_the_flags_or_none_if_it_cannot_ask():
    flags = {"pending": False, "safety_hold": False, "queued": 0}
    assert session_busy(1, _client(lambda r: httpx.Response(200, json=flags))) == flags
    assert session_busy(1, _client(lambda r: httpx.Response(500))) is None


# ---- screen attributes for deliveries and for closing ---------------------------------------------------------
def test_delivery_attributes_carry_the_screen_the_item_and_the_exact_line():
    assert delivery_attributes(ITEM, 5) == {
        "arjun.screen": "medicine", "arjun.turn": "5", "arjun.reply": ITEM["text"], "arjun.item": "dose:4",
    }


def test_closed_attributes_tell_the_app_this_is_a_normal_end_not_a_dropped_connection():
    assert closed_attributes(9) == {"arjun.screen": "closed", "arjun.turn": "9", "arjun.reply": "", "arjun.item": ""}


def test_ordinary_replies_clear_the_item():
    from bridge import BridgeReply

    attrs = attributes_for(BridgeReply("x", "care", False, 1.0), 2)
    assert attrs["arjun.item"] == ""


def test_every_event_gets_a_larger_turn_number_so_the_app_can_tell_them_apart(tmp_path):
    log = TurnLog("mr-IN", tmp_path / "t.jsonl")
    first = log.bump()
    log.final_transcript(1.0, "x", None)  # a spoken turn takes the next number
    assert log.bump() == first + 2
