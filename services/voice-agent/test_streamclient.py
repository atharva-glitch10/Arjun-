"""StreamClient (2026-11-10): ordering, cancel on barge-in, reconnect back-off, HTTP fallback, no replay after an ack."""

import asyncio
import json

import pytest
import streamclient
from bridge import BridgeReply
from streamclient import StreamClient, StreamLost, ask_with_fallback

FINAL = {"type": "final", "reply": "ठीक आहे. चला.", "mode": "chat", "awaiting_confirmation": False, "intent": "chat",
         "language": "mr", "speech": "", "source": "llm", "silent": False}


class FakeWs:
    """A server script: on a `turn` frame it answers with `script(frame)` frames; on `cancel` it records it."""

    def __init__(self, script):
        self.script, self.sent, self.q, self.closed = script, [], asyncio.Queue(), False

    async def send(self, raw):
        f = json.loads(raw)
        self.sent.append(f)
        if f["type"] == "turn":
            for m in self.script(f):
                self.q.put_nowait(json.dumps({"turn_id": f["turn_id"], **m}) if m is not None else None)

    def __aiter__(self):
        return self

    async def __anext__(self):
        m = await self.q.get()
        if m is None:
            raise ConnectionError("closed")
        return m

    async def close(self):
        self.closed = True


def happy(f):
    return [{"type": "ack", "filler": "", "language": "mr"}, {"type": "sentence", "seq": 0, "text": "ठीक आहे."},
            {"type": "sentence", "seq": 1, "text": "चला."}, FINAL]


def client_for(script, ws_list=None, clock=None):
    ws = FakeWs(script)
    calls = {"n": 0}

    async def connect(url):
        calls["n"] += 1
        if ws_list is not None:
            nxt = ws_list.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt
        return ws

    c = StreamClient(url="ws://x/turn/stream", key="", connect=connect, **({"clock": clock} if clock else {}))
    return c, ws, calls


def run(coro):
    return asyncio.run(coro)


def test_a_turn_returns_the_final_as_a_bridge_reply_and_reports_sentences():
    async def go():
        c, ws, _ = client_for(happy)
        got, acks = [], []
        r = await c.ask(7, "नमस्कार", "mr-IN", "hi", on_ack=acks.append, on_sentence=lambda i, t: got.append((i, t)))
        await c.close()
        return r, got, acks, ws

    r, got, acks, ws = run(go())
    assert isinstance(r, BridgeReply) and r.text == "ठीक आहे. चला." and r.mode == "chat" and r.language == "mr"
    assert got == [(0, "ठीक आहे."), (1, "चला.")] and acks[0]["type"] == "ack"
    assert ws.sent[0]["user"] == 7 and ws.sent[0]["lang"] == "mr-IN" and ws.sent[0]["reply_language"] == "hi" and ws.sent[0]["turn_id"]


def test_turn_ids_are_unique_and_turns_in_a_row_work():
    async def go():
        c, ws, calls = client_for(happy)
        a = await c.ask(1, "एक")
        b = await c.ask(1, "दोन")
        await c.close()
        return a, b, ws, calls

    a, b, ws, calls = run(go())
    assert a.text == b.text and len({f["turn_id"] for f in ws.sent}) == 2 and calls["n"] == 1  # one socket reused


def test_cancelling_the_ask_sends_cancel_so_the_server_drops_the_turn():
    async def go():
        c, ws, _ = client_for(lambda f: [{"type": "ack", "filler": "", "language": "mr"}])  # never finishes
        t = asyncio.create_task(c.ask(1, "x"))
        await asyncio.sleep(0.05)
        t.cancel()  # barge-in / tap
        with pytest.raises(asyncio.CancelledError):
            await t
        await c.close()
        return ws

    ws = run(go())
    assert [f["type"] for f in ws.sent] == ["turn", "cancel"] and ws.sent[1]["turn_id"] == ws.sent[0]["turn_id"]


def test_no_connection_means_none_so_http_answers_and_backoff_grows(monkeypatch):
    now = [100.0]

    async def go():
        c, _, calls = client_for(happy, ws_list=[OSError("refused"), OSError("refused"), FakeWs(happy)], clock=lambda: now[0])
        r1 = await c.ask(1, "x")  # refused -> None, backing off 1 s
        r2 = await c.ask(1, "x")  # still backing off: not even tried
        now[0] += 1.1
        r3 = await c.ask(1, "x")  # second refusal -> backoff 2 s
        now[0] += 1.0
        r4 = await c.ask(1, "x")  # inside the 2 s
        now[0] += 1.5
        r5 = await c.ask(1, "x")  # reconnects
        await c.close()
        return [r1, r2, r3, r4], r5, calls, c

    nones, r5, calls, c = run(go())
    assert nones == [None] * 4 and r5.text == "ठीक आहे. चला." and calls["n"] == 3 and c.stats["failures"] == 2 and c._backoff == 1.0  # reset after success


def test_a_dead_socket_before_the_ack_returns_none_for_the_http_path():
    async def go():
        c, _, _ = client_for(lambda f: [None])  # server dies at once
        return await c.ask(1, "x")

    assert run(go()) is None


def test_a_dead_socket_after_the_ack_raises_stream_lost_never_replays():
    async def go():
        c, _, _ = client_for(lambda f: [{"type": "ack", "filler": "", "language": "mr"}, None])
        with pytest.raises(StreamLost):
            await c.ask(1, "उद्या सकाळी १० ला औषध आठवण करून दे")

    run(go())


def test_ask_with_fallback_uses_http_only_when_the_turn_never_started():
    async def go(script):
        c, _, _ = client_for(script)
        calls = []

        async def http():
            calls.append(1)
            return BridgeReply(text="HTTP", mode="chat", awaiting_confirmation=False, round_trip_ms=1)

        r = await ask_with_fallback(c, 1, "नमस्कार", "mr-IN", "mr", http_ask=http)
        await c.close()
        return r, calls

    r, calls = run(go(lambda f: [None]))  # died before ack -> HTTP
    assert r.text == "HTTP" and calls == [1]
    r, calls = run(go(lambda f: [{"type": "ack", "filler": "", "language": "mr"}, None]))  # died after ack -> fixed line, NO http
    assert calls == [] and r.mode == "fallback" and r.text and r.text != "HTTP"
    r, calls = run(go(happy))
    assert r.text == "ठीक आहे. चला." and calls == []


def test_an_emergency_that_loses_the_socket_after_ack_still_speaks_the_safety_line():
    async def go():
        c, _, _ = client_for(lambda f: [{"type": "ack", "filler": "", "language": "mr"}, None])
        return await ask_with_fallback(c, 1, "मला छातीत दुखतंय", "mr-IN", "mr", http_ask=lambda: None)

    r = run(go())
    assert r.mode == "safety" and r.text


def test_server_refusals_before_the_engine_ran_go_to_http():
    async def go(status):
        c, _, _ = client_for(lambda f: [{"type": "error", "status": status, "detail": "x"}])
        return await c.ask(1, "x")

    assert run(go(429)) is None and run(go(422)) is None


def test_enabled_flag_and_url(monkeypatch):
    monkeypatch.delenv("ARJUN_STREAM", raising=False)
    assert not streamclient.enabled()
    monkeypatch.setenv("ARJUN_STREAM", "1")
    assert streamclient.enabled()
    assert streamclient.ws_url("http://127.0.0.1:8001") == "ws://127.0.0.1:8001/turn/stream"
    assert streamclient.ws_url("https://r.example/") == "wss://r.example/turn/stream"


def test_the_key_goes_in_a_header_and_never_in_a_log(caplog, monkeypatch):
    seen = {}

    class FakeWebsockets:
        @staticmethod
        async def connect(url, additional_headers=None, **kw):
            seen["headers"], seen["url"] = additional_headers, url
            raise OSError("refused")

    import sys

    monkeypatch.setitem(sys.modules, "websockets", FakeWebsockets)

    async def go():
        c = StreamClient(url="ws://x/turn/stream", key="secret-key-42")
        return await c.ask(1, "x")

    assert run(go()) is None
    assert seen["headers"] == {"x-arjun-internal": "secret-key-42"} and "secret-key-42" not in caplog.text and "secret-key-42" not in seen["url"]
