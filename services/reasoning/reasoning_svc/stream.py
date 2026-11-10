"""WebSocket transport for one turn at a time: /turn/stream (2026-11-10).

Client -> server (JSON text frames):
  {"type": "turn", "user": 7, "text": "...", "lang": "mr-IN", "turn_id": "t1", "reply_language": "hi"}   (type/lang/reply_language optional)
  {"type": "cancel", "turn_id": "t1"}                                      (barge-in / tap: drop whatever is not yet spoken)
Server -> client, per turn, in this order:
  {"type": "ack", "turn_id", "filler", "language"}          at once (rules only, no LLM): the web-lookup filler, else ""
  {"type": "sentence", "turn_id", "seq", "text"}            one per complete sentence of what is to be SPOKEN (guards already applied)
  {"type": "final", "turn_id", "reply", "speech", "intent", "mode", "language", ...}   the full /turn result (same fields as TurnOut)
  {"type": "action", "turn_id", "action"}                   only when the screen should open / do something
  {"type": "error", "turn_id", "status", "detail"} or {"type": "cancelled", "turn_id"}
The safety rules run first inside the engine, exactly as for /turn; an emergency / distress sentence is never rate limited and
never gets a filler. Sentences are cut from the FINISHED, guarded reply (the language, medical-advice and relevance guards need
the whole text), so no unguarded token is ever spoken. Turns of one user are served strictly in arrival order."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import re
from collections.abc import Callable
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from .core_client import CoreError
from .distress import is_distress, is_emergency

log = logging.getLogger("reasoning.stream")

_END = re.compile(r"(?<=[.!?।॥])\s+|\n+")
_REPLY_LANG = re.compile(r"^(mr|hi|en|bn|gu|kn|ml|pa|ta|te|or)$")
MAX_TEXT = 2000
INTERNAL_KEY_HEADER = "x-arjun-internal"


def split_sentences(text: str) -> list[str]:
    """Complete sentences, in order, none empty. A voice tag such as <laugh> stays with its sentence."""
    out = [p.strip() for p in _END.split(text or "") if p and p.strip()]
    return out or ([text.strip()] if text and text.strip() else [])


def key_ok(ws: WebSocket) -> bool:
    """Optional shared key (ARJUN_INTERNAL_KEY; the value is never logged). Unset = open, as /turn is: it is an internal port."""
    want = os.environ.get("ARJUN_INTERNAL_KEY", "")
    if not want:
        return True
    got = ws.headers.get(INTERNAL_KEY_HEADER, "")
    return hmac.compare_digest(got.encode(), want.encode())


def _safe(fn: Callable[..., None], *a: Any) -> None:
    try:
        fn(*a)
    except Exception as exc:  # noqa: BLE001
        log.warning("after_turn failed: %s", type(exc).__name__)


async def serve(
    ws: WebSocket,
    get_engine: Callable[[], Any],
    bucket: Any,
    after_turn: Callable[[int, str, Any], None],
) -> None:
    if not key_ok(ws):
        await ws.close(code=4401)  # refused before accept
        return
    await ws.accept()
    send_lock = asyncio.Lock()
    user_locks: dict[int, asyncio.Lock] = {}
    cancelled: set[str] = set()
    tasks: set[asyncio.Task[None]] = set()

    async def send(obj: dict[str, Any]) -> None:
        async with send_lock:
            await ws.send_text(json.dumps(obj, ensure_ascii=False))

    async def run(msg: dict[str, Any]) -> None:
        tid = str(msg["turn_id"])
        user = msg["user"]
        text = str(msg["text"])
        lang = msg.get("lang") or None
        rlang = msg.get("reply_language") or None
        engine = get_engine()
        safety = is_emergency(text) or is_distress(text)
        async with user_locks.setdefault(user, asyncio.Lock()):  # per-user ordering (asyncio locks are FIFO)
            if tid in cancelled:
                await send({"type": "cancelled", "turn_id": tid})
                return
            wait = bucket.take(str(user))
            if wait > 0 and not safety:
                await send({"type": "error", "turn_id": tid, "status": 429, "detail": "too many turns"})
                return
            prep = engine.prepare(text, lang, rlang)  # rules only: milliseconds
            await send({"type": "ack", "turn_id": tid, "filler": "" if safety else prep.get("filler", ""), "language": prep.get("language", "")})
            try:
                res = await asyncio.to_thread(engine.handle, user, text, lang, reply_language=rlang)
            except CoreError as exc:
                await send({"type": "error", "turn_id": tid, "status": 502 if exc.status >= 500 else exc.status, "detail": str(exc.detail)})
                return
            except Exception as exc:  # noqa: BLE001 - never a silent socket: the client falls back to HTTP /turn
                log.warning("stream turn failed: %s", type(exc).__name__)
                await send({"type": "error", "turn_id": tid, "status": 500, "detail": type(exc).__name__})
                return
            if tid in cancelled:  # she spoke / tapped meanwhile: nothing of this turn is spoken
                await send({"type": "cancelled", "turn_id": tid})
                return
            if not res.silent:
                for i, s in enumerate(split_sentences(res.speech or res.reply)):
                    if tid in cancelled:
                        await send({"type": "cancelled", "turn_id": tid})
                        return
                    await send({"type": "sentence", "turn_id": tid, "seq": i, "text": s})
            await send({"type": "final", "turn_id": tid, **res.__dict__})
            if (res.action or {}).get("type", "none") != "none":
                await send({"type": "action", "turn_id": tid, "action": res.action})
            await asyncio.to_thread(_safe, after_turn, user, text, res)  # note_activity + the family summary: after the words went out

    try:
        while True:
            try:
                msg = json.loads(await ws.receive_text())
            except json.JSONDecodeError:
                await send({"type": "error", "turn_id": "", "status": 400, "detail": "bad json"})
                continue
            if not isinstance(msg, dict):
                continue
            tid = str(msg.get("turn_id") or "")
            if msg.get("type", "turn") == "cancel":
                cancelled.add(tid)
                continue
            rl = msg.get("reply_language")
            ok = (
                isinstance(msg.get("user"), int) and isinstance(msg.get("text"), str) and 0 < len(msg["text"]) <= MAX_TEXT
                and bool(tid) and (rl is None or (isinstance(rl, str) and bool(_REPLY_LANG.match(rl))))
            )
            if not ok:
                await send({"type": "error", "turn_id": tid, "status": 422, "detail": "bad turn"})
                continue
            t = asyncio.create_task(run(msg))
            tasks.add(t)
            t.add_done_callback(tasks.discard)
    except WebSocketDisconnect:
        pass
    finally:
        for t in list(tasks):
            t.cancel()
