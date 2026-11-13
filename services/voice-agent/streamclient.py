"""Client of reasoning's WebSocket /turn/stream (2026-11-10). One socket per worker, reconnect with back-off, per-turn queues.

`StreamClient.ask(...)` returns a BridgeReply built from the `final` frame, or None when the turn never reached the server
(socket down / refused / no ack): the caller then uses the unchanged HTTP /turn. If the socket dies AFTER the server
acknowledged the turn, the turn may already have been acted on, so it is NOT replayed over HTTP (a reminder would be set
twice): `ask` raises StreamLost and the caller speaks the fixed fallback line. `ARJUN_STREAM=1` turns the client on.
Frames are documented in services/reasoning/reasoning_svc/stream.py. The shared key (ARJUN_INTERNAL_KEY) is sent as a header
and never logged."""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import logging
import os
import time
from collections.abc import Callable

from bridge import REASONING_TIMEOUT_S, REASONING_URL, BridgeReply, reply_from_data

log = logging.getLogger("arjun.stream")

BACKOFF_START_S = 1.0
BACKOFF_MAX_S = 30.0
CONNECT_TIMEOUT_S = float(os.environ.get("ARJUN_STREAM_CONNECT_S", "1.5"))
ACK_TIMEOUT_S = float(os.environ.get("ARJUN_STREAM_ACK_S", "2.0"))  # the ack is rules only: if it is later than this, use HTTP


class StreamLost(Exception):
    """The socket died after the server had accepted the turn: do not replay it over HTTP."""


def enabled() -> bool:
    return os.environ.get("ARJUN_STREAM", "").strip() == "1"


def ws_url(base: str = REASONING_URL) -> str:
    return base.replace("https://", "wss://", 1).replace("http://", "ws://", 1).rstrip("/") + "/turn/stream"


class StreamClient:
    def __init__(self, url: str | None = None, key: str | None = None, connect: Callable | None = None, clock: Callable[[], float] = time.monotonic) -> None:  # type: ignore[type-arg]
        self.url = url or ws_url()
        self.key = os.environ.get("ARJUN_INTERNAL_KEY", "") if key is None else key
        self._connect = connect  # tests inject a fake
        self._clock = clock
        self._ws = None
        self._reader: asyncio.Task[None] | None = None
        self._queues: dict[str, asyncio.Queue[dict | None]] = {}  # type: ignore[type-arg]
        self._lock = asyncio.Lock()
        self._ids = itertools.count(1)
        self._backoff = BACKOFF_START_S
        self._down_until = 0.0
        self.stats = {"connects": 0, "failures": 0}

    # ---- connection -------------------------------------------------------------------------------------------
    def _fail(self) -> None:
        self.stats["failures"] += 1
        self._down_until = self._clock() + self._backoff
        self._backoff = min(self._backoff * 2, BACKOFF_MAX_S)
        self._ws = None

    async def _ensure(self) -> bool:
        if self._ws is not None:
            return True
        if self._clock() < self._down_until:  # still backing off: do not even try, the caller uses HTTP
            return False
        async with self._lock:
            if self._ws is not None:
                return True
            try:
                if self._connect is not None:
                    ws = await asyncio.wait_for(self._connect(self.url), CONNECT_TIMEOUT_S)
                else:
                    import websockets

                    headers = {"x-arjun-internal": self.key} if self.key else {}
                    ws = await asyncio.wait_for(
                        websockets.connect(self.url, additional_headers=headers, open_timeout=CONNECT_TIMEOUT_S, ping_interval=20, max_size=1 << 20),
                        CONNECT_TIMEOUT_S + 0.5,
                    )
            except Exception as exc:  # noqa: BLE001
                log.warning("stream connect failed (%s); HTTP /turn until %.0f s from now", type(exc).__name__, self._backoff)
                self._fail()
                return False
            self._ws = ws
            self._backoff = BACKOFF_START_S
            self.stats["connects"] += 1
            self._reader = asyncio.create_task(self._read(ws), name="turn-stream-reader")
            return True

    async def _read(self, ws) -> None:  # type: ignore[no-untyped-def]
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                q = self._queues.get(str(msg.get("turn_id", "")))
                if q is not None:
                    q.put_nowait(msg)
        except Exception as exc:  # noqa: BLE001
            log.warning("stream closed (%s)", type(exc).__name__)
        finally:
            if self._ws is ws:
                self._fail()
            for q in self._queues.values():
                q.put_nowait(None)  # every waiting turn learns the socket is gone

    async def close(self) -> None:
        ws, self._ws = self._ws, None
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.close()
        if self._reader:
            self._reader.cancel()

    # ---- one turn ---------------------------------------------------------------------------------------------
    async def cancel(self, turn_id: str) -> None:
        ws = self._ws
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.send(json.dumps({"type": "cancel", "turn_id": turn_id}))

    async def ask(
        self,
        user_id: int,
        text: str,
        language: str | None = None,
        reply_language: str | None = None,
        on_ack: Callable[[dict], None] | None = None,  # type: ignore[type-arg]
        on_sentence: Callable[[int, str], None] | None = None,
        on_llm_sentence: Callable[[int, str, str], None] | None = None,
        timeout: float = REASONING_TIMEOUT_S,
    ) -> BridgeReply | None:
        if not await self._ensure():
            return None
        ws = self._ws
        tid = f"t{next(self._ids)}"
        q: asyncio.Queue[dict | None] = asyncio.Queue()  # type: ignore[type-arg]
        self._queues[tid] = q
        t0 = time.perf_counter()
        frame = {"type": "turn", "turn_id": tid, "user": user_id, "text": text}
        if language:
            frame["lang"] = language
        if reply_language:
            frame["reply_language"] = reply_language
        acked = False
        done = False
        try:
            try:
                await ws.send(json.dumps(frame, ensure_ascii=False))  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001
                self._fail()
                return None
            deadline = self._clock() + timeout
            while True:
                limit = (deadline if acked else min(deadline, self._clock() + ACK_TIMEOUT_S)) - self._clock()
                try:
                    msg = await asyncio.wait_for(q.get(), max(0.05, limit))
                except asyncio.TimeoutError:
                    if not acked:
                        await self.cancel(tid)  # never reached the engine in time: the HTTP path answers, this one must not
                        return None
                    raise StreamLost("timeout after ack") from None
                if msg is None:
                    if not acked:
                        return None
                    raise StreamLost("socket closed after ack")
                kind = msg.get("type")
                if kind == "ack":
                    acked = True
                    if on_ack:
                        on_ack(msg)
                elif kind == "sentence":
                    seq, sentence = int(msg.get("seq", 0)), str(msg.get("text", ""))
                    if on_sentence:
                        on_sentence(seq, sentence)
                    if (
                        on_llm_sentence and seq == 0 and msg.get("source") == "llm"
                        and msg.get("mode") in ("chat", "companion")
                    ):
                        on_llm_sentence(seq, sentence, str(msg.get("language") or ""))
                elif kind == "final":
                    done = True
                    return reply_from_data(msg, language, (time.perf_counter() - t0) * 1000)
                elif kind == "error":
                    done = True
                    if not acked or msg.get("status") in (400, 422, 429):
                        return None  # refused before the engine ran: HTTP answers (and applies its own limits)
                    raise StreamLost(f"server error {msg.get('status')}")
                elif kind == "cancelled":
                    done = True
                    raise asyncio.CancelledError
        except asyncio.CancelledError:
            if not done:
                await self.cancel(tid)  # barge-in / tap: drop whatever has not been spoken
            raise
        finally:
            self._queues.pop(tid, None)


async def ask_with_fallback(
    client: StreamClient,
    user_id: int,
    text: str,
    language: str,
    reply_language: str | None = None,
    http_ask: Callable | None = None,  # type: ignore[type-arg]
    on_sentence: Callable[[int, str], None] | None = None,
    on_llm_sentence: Callable[[int, str, str], None] | None = None,
) -> BridgeReply:
    """Stream first; the unchanged HTTP /turn (reply_or_fallback) when the turn never reached the server; the fixed fallback
    line when the socket died after the server accepted it (replaying could act twice). Never silent, never raises."""
    from bridge import fallback_text, reply_or_fallback
    from safety_words import is_distress, is_emergency

    http_ask = http_ask or (lambda: asyncio.to_thread(reply_or_fallback, user_id, text, language, None, reply_language))
    t0 = time.perf_counter()
    try:
        got = await client.ask(
            user_id, text, language, reply_language, on_sentence=on_sentence, on_llm_sentence=on_llm_sentence,
        )
    except StreamLost as exc:
        lang = reply_language or language
        log.error("stream lost after ack (%s): fixed fallback, no HTTP replay", exc)
        line = fallback_text(lang, text)
        return BridgeReply(
            text=line, mode="safety" if is_emergency(text) or is_distress(text) else "fallback", awaiting_confirmation=False,
            round_trip_ms=(time.perf_counter() - t0) * 1000, language=lang, silent=not bool(line),
        )
    if got is not None:
        return got
    return await http_ask()
