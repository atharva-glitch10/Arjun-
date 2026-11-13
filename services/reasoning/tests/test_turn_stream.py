"""WebSocket /turn/stream (2026-11-10): frame order, sentences, per-user ordering, cancel, auth, limits, parity with /turn."""

import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from reasoning_svc import main as reasoning_main
from reasoning_svc.core_client import CoreClient, CoreError
from reasoning_svc.stream import split_sentences
from reasoning_svc.turn import TurnEngine
from test_web_search import NOW


def result(reply="ठीक आहे. मी इथे आहे! तुम्ही कसे आहात?", **kw):
    base = dict(reply=reply, intent="chat", mode="chat", language="mr", awaiting_confirmation=False, screen="reply", speech="",
                action={"type": "none", "kind": "", "value": "", "title": ""}, source="llm", trace={}, silent=False,
                filler="", active_language="", speech_style={"rate": "normal", "volume": "normal", "simple": False})
    base.update(kw)
    return SimpleNamespace(**base)


class FakeEngine:
    def __init__(self, res=None, delay=0.0, exc=None):
        self.res, self.delay, self.exc = res or result(), delay, exc
        self.handled, self.noted, self.active = [], [], 0
        self.max_active = 0
        self._l = threading.Lock()

    def prepare(self, text, language_code=None, reply_language=None):
        return {"needs_web": False, "filler": "बघतो…" if "पाऊस" in text else "", "hold": "", "language": reply_language or "mr"}

    def handle(self, user, text, language_code=None, reply_language=None):
        with self._l:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(self.delay)
        with self._l:
            self.active -= 1
        if self.exc:
            raise self.exc
        self.handled.append((user, text, language_code, reply_language))
        return self.res

    def note_activity(self, user):
        self.noted.append(user)


class Bucket:
    def __init__(self, wait=0):
        self.wait = wait

    def take(self, key):
        return self.wait


@pytest.fixture()
def setup(monkeypatch):
    def build(engine=None, bucket=None):
        eng = engine or FakeEngine()
        monkeypatch.setattr(reasoning_main, "get_engine", lambda: eng)
        monkeypatch.setattr(reasoning_main, "_turn_bucket", bucket or Bucket())
        monkeypatch.setattr(reasoning_main, "get_tracker", lambda: SimpleNamespace(record=lambda *a, **k: None))
        monkeypatch.delenv("ARJUN_INTERNAL_KEY", raising=False)
        return TestClient(reasoning_main.app), eng

    return build


def turn(user=1, text="नमस्कार", tid="t1", **kw):
    return {"type": "turn", "user": user, "text": text, "turn_id": tid, **kw}


def collect(ws, tid, until=("final", "error", "cancelled")):
    out = []
    while True:
        m = ws.receive_json()
        if m.get("turn_id") == tid:
            out.append(m)
            if m["type"] in until:
                return out


def test_frames_come_in_order_ack_sentences_final(setup):
    client, eng = setup()
    with client.websocket_connect("/turn/stream") as ws:
        ws.send_json(turn(lang="mr-IN", reply_language="hi"))
        frames = collect(ws, "t1")
    assert [f["type"] for f in frames] == ["ack", "sentence", "sentence", "sentence", "final"]
    assert [f["text"] for f in frames if f["type"] == "sentence"] == ["ठीक आहे.", "मी इथे आहे!", "तुम्ही कसे आहात?"]
    assert [f["seq"] for f in frames if f["type"] == "sentence"] == [0, 1, 2]
    assert all(f["source"] == "llm" and f["mode"] == "chat" and f["language"] == "mr"
               for f in frames if f["type"] == "sentence")
    final = frames[-1]
    assert final["reply"] == result().reply and final["intent"] == "chat" and final["language"] == "mr"
    assert eng.handled == [(1, "नमस्कार", "mr-IN", "hi")]  # the same engine call /turn makes, parameters carried


def test_the_web_filler_rides_the_ack(setup):
    client, _ = setup()
    with client.websocket_connect("/turn/stream") as ws:
        ws.send_json(turn(text="उद्या पाऊस पडेल का"))
        assert collect(ws, "t1")[0]["filler"] == "बघतो…"


def test_speech_with_voice_tags_is_what_is_split(setup):
    client, _ = setup(FakeEngine(result(reply="छान. मस्त.", speech="<laugh> छान. मस्त.")))
    with client.websocket_connect("/turn/stream") as ws:
        ws.send_json(turn())
        s = [f["text"] for f in collect(ws, "t1") if f["type"] == "sentence"]
    assert s == ["<laugh> छान.", "मस्त."]


def test_a_silent_result_speaks_no_sentence(setup):
    client, _ = setup(FakeEngine(result(reply="", silent=True)))
    with client.websocket_connect("/turn/stream") as ws:
        ws.send_json(turn())
        assert [f["type"] for f in collect(ws, "t1")] == ["ack", "final"]


def test_an_action_frame_follows_final(setup):
    act = {"type": "open_video", "kind": "video", "value": "abc", "title": "भजन"}
    client, _ = setup(FakeEngine(result(reply="लावतो.", action=act)))
    with client.websocket_connect("/turn/stream") as ws:
        ws.send_json(turn())
        frames = collect(ws, "t1", until=("action",))
    assert frames[-1] == {"type": "action", "turn_id": "t1", "action": act}


def test_after_turn_notes_activity_and_records(setup, monkeypatch):
    recorded = []
    client, eng = setup()
    monkeypatch.setattr(reasoning_main, "get_tracker", lambda: SimpleNamespace(record=lambda *a: recorded.append(a)))
    with client.websocket_connect("/turn/stream") as ws:
        ws.send_json(turn(user=9))
        collect(ws, "t1")
        ws.send_json(turn(user=9, tid="t2"))
        collect(ws, "t2")  # the second turn's frames prove the first one's after-work (it runs before the lock is released) finished
    assert eng.noted == [9, 9] and len(recorded) == 2


def test_turns_of_one_user_are_served_one_at_a_time_in_arrival_order(setup):
    client, eng = setup(FakeEngine(delay=0.15))
    with client.websocket_connect("/turn/stream") as ws:
        for i in range(3):
            ws.send_json(turn(text=f"एक {i}", tid=f"t{i}"))
        done = []
        while len(done) < 3:
            m = ws.receive_json()
            if m["type"] == "final":
                done.append(m["turn_id"])
    assert done == ["t0", "t1", "t2"] and eng.max_active == 1
    assert [h[1] for h in eng.handled] == ["एक 0", "एक 1", "एक 2"]


def test_different_users_do_not_wait_for_each_other(setup):
    client, eng = setup(FakeEngine(delay=0.3))
    with client.websocket_connect("/turn/stream") as ws:
        ws.send_json(turn(user=1, tid="a"))
        ws.send_json(turn(user=2, tid="b"))
        finals = 0
        while finals < 2:
            finals += ws.receive_json()["type"] == "final"
    assert eng.max_active == 2


def test_cancel_before_it_runs_drops_the_turn_and_nothing_is_handled(setup):
    client, eng = setup(FakeEngine(delay=0.3))
    with client.websocket_connect("/turn/stream") as ws:
        ws.send_json(turn(tid="first"))
        ws.send_json(turn(tid="second"))  # waits behind "first"
        ws.send_json({"type": "cancel", "turn_id": "second"})
        got = collect(ws, "second")
    assert got[-1]["type"] == "cancelled" and [h[1] for h in eng.handled] == ["नमस्कार"]


def test_cancel_while_running_speaks_nothing(setup):
    client, _ = setup(FakeEngine(delay=0.4))
    with client.websocket_connect("/turn/stream") as ws:
        ws.send_json(turn(tid="x"))
        assert ws.receive_json()["type"] == "ack"
        ws.send_json({"type": "cancel", "turn_id": "x"})  # barge-in: she spoke while the engine was working
        rest = collect(ws, "x")
    assert [f["type"] for f in rest] == ["cancelled"]


@pytest.mark.parametrize("bad", [
    {"type": "turn", "user": "1", "text": "x", "turn_id": "t"},
    {"type": "turn", "user": 1, "text": "", "turn_id": "t"},
    {"type": "turn", "user": 1, "text": "x" * 2001, "turn_id": "t"},
    {"type": "turn", "user": 1, "text": "x"},
    {"type": "turn", "user": 1, "text": "x", "turn_id": "t", "reply_language": "hindi"},
])
def test_a_malformed_turn_gets_422_and_the_socket_lives(setup, bad):
    client, eng = setup()
    with client.websocket_connect("/turn/stream") as ws:
        ws.send_json(bad)
        e = ws.receive_json()
        assert e["type"] == "error" and e["status"] == 422
        ws.send_json(turn(tid="ok"))
        assert collect(ws, "ok")[-1]["type"] == "final"


def test_bad_json_is_an_error_frame_not_a_crash(setup):
    client, _ = setup()
    with client.websocket_connect("/turn/stream") as ws:
        ws.send_text("{nope")
        assert ws.receive_json()["status"] == 400


def test_rate_limit_applies_but_never_to_a_safety_sentence(setup):
    client, eng = setup(bucket=Bucket(wait=5))
    with client.websocket_connect("/turn/stream") as ws:
        ws.send_json(turn(text="गप्पा मारू", tid="a"))
        assert collect(ws, "a")[-1]["status"] == 429
        ws.send_json(turn(text="मला छातीत दुखतंय", tid="b"))
        frames = collect(ws, "b")
    assert frames[-1]["type"] == "final" and frames[0]["filler"] == ""  # no filler on a safety turn
    assert [h[1] for h in eng.handled] == ["मला छातीत दुखतंय"]


def test_an_engine_failure_is_an_error_frame_so_the_client_can_fall_back(setup):
    client, _ = setup(FakeEngine(exc=CoreError(503, "down")))
    with client.websocket_connect("/turn/stream") as ws:
        ws.send_json(turn())
        last = collect(ws, "t1")[-1]
    assert last["type"] == "error" and last["status"] == 502
    client, _ = setup(FakeEngine(exc=RuntimeError("boom")))
    with client.websocket_connect("/turn/stream") as ws:
        ws.send_json(turn())
        assert collect(ws, "t1")[-1]["status"] == 500


def test_the_shared_key_is_enforced_when_configured(setup, monkeypatch):
    client, _ = setup()
    monkeypatch.setenv("ARJUN_INTERNAL_KEY", "k-test")
    with pytest.raises(Exception):  # noqa: B017 - closed before accept
        with client.websocket_connect("/turn/stream") as ws:
            ws.send_json(turn())
            ws.receive_json()
    with pytest.raises(Exception):  # noqa: B017
        with client.websocket_connect("/turn/stream", headers={"x-arjun-internal": "wrong"}) as ws:
            ws.receive_json()
    with client.websocket_connect("/turn/stream", headers={"x-arjun-internal": "k-test"}) as ws:
        ws.send_json(turn())
        assert collect(ws, "t1")[-1]["type"] == "final"


def test_the_key_value_is_never_logged(setup, monkeypatch, caplog):
    client, _ = setup()
    monkeypatch.setenv("ARJUN_INTERNAL_KEY", "super-secret-key-9")
    with client.websocket_connect("/turn/stream", headers={"x-arjun-internal": "super-secret-key-9"}) as ws:
        ws.send_json(turn())
        collect(ws, "t1")
    assert "super-secret-key-9" not in caplog.text


def test_split_sentences_handles_danda_question_and_newline():
    assert split_sentences("ठीक आहे। चला! का?\nहो") == ["ठीक आहे।", "चला!", "का?", "हो"]
    assert split_sentences("एकच वाक्य") == ["एकच वाक्य"] and split_sentences("   ") == []


def test_parity_with_http_turn_on_the_real_engine(core_http, uid, monkeypatch):
    """Same words, same fields: the streamed final equals what POST /turn returns (rules path, no LLM)."""
    monkeypatch.setattr(reasoning_main, "_turn_bucket", Bucket())
    monkeypatch.delenv("ARJUN_INTERNAL_KEY", raising=False)
    eng = TurnEngine(CoreClient(core_http), evon=None, clock=lambda: NOW, ask_first=False)
    monkeypatch.setattr(reasoning_main, "_engine", eng)
    client = TestClient(reasoning_main.app)
    http = client.post("/turn", json={"user_id": uid, "text": "आज काय आहे", "reply_language": "hi"}).json()
    with client.websocket_connect("/turn/stream") as ws:
        ws.send_json(turn(user=uid, text="आज काय आहे", reply_language="hi"))
        final = collect(ws, "t1")[-1]
    for k in ("reply", "intent", "mode", "language", "screen", "source", "silent"):
        assert final[k] == http[k], k
