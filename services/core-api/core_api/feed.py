"""The family's live feed: every alert and wellbeing line, pushed over a WebSocket, with REST polling as fallback.

    browser ──WS /ws/users/{id}/feed──▶ core-api      (push: sent the moment a row is committed)
    browser ──GET /users/{id}/feed?after=N──▶ core-api (poll: same rows, same ids; used when the WS is down)

How a row gets here: a SQLAlchemy `before_flush` hook turns every new Notification / Wellbeing into a FeedEvent,
so no endpoint can forget to publish. After the commit, `BROKER.notify(user_id)` wakes the open sockets of that
user (thread-safe: sync endpoints run in a worker thread, sockets live on the event loop). A socket also re-checks
the table every few seconds, so a row written by another process is never missed, only delayed.

Single process, in memory: with more than one core-api replica the push still works per replica and the
periodic re-check covers the rest. Seriousness levels: info < normal < watch < urgent < emergency.
"""

from __future__ import annotations

import asyncio
import hmac
import os
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from . import models as m
from .db import get_db
from .deps import require_key, testing

router = APIRouter(dependencies=[Depends(require_key)])
ws_router = APIRouter()  # WebSockets authenticate themselves (browsers cannot always set headers on a WS)

SEVERITIES = ("info", "normal", "watch", "urgent", "emergency")
RANK = {s: i for i, s in enumerate(SEVERITIES)}

# Notification kind -> (seriousness, short title for the family)
_KINDS: dict[str, tuple[str, str]] = {
    "emergency": ("emergency", "Emergency"),
    "distress": ("urgent", "She may be upset"),
    "caregiver_request": ("urgent", "She asked for help"),
    "issue": ("urgent", "She is facing an issue"),
    "lonely": ("watch", "She said she feels lonely"),
    "health_complaint": ("watch", "A health complaint was mentioned"),
    "medicine_not_taken": ("watch", "Medicine not taken"),
    "medicine_unconfirmed": ("watch", "Medicine not confirmed"),
    "checkin": ("info", "Check-in"),
    "undelivered": ("watch", "Reminder not delivered"),
    "help_cancelled": ("info", "Help request cancelled"),
}


def notification_severity(kind: str) -> tuple[str, str]:
    return _KINDS.get(kind, ("info", kind.replace("_", " ").capitalize()))


def max_severity(*levels: str) -> str:
    return max((x for x in levels if x in RANK), key=RANK.__getitem__, default="normal")


# ---- publish: every new Notification / Wellbeing becomes a FeedEvent ---------------------------------------
@event.listens_for(Session, "before_flush")
def _to_feed(session: Session, _ctx: object, _instances: object) -> None:
    for obj in list(session.new):
        if isinstance(obj, m.Notification):
            severity, title = notification_severity(obj.kind)
            fe = m.FeedEvent(user_id=obj.user_id, kind=obj.kind, severity=severity, title=title, body=obj.body or "")
        elif isinstance(obj, m.Wellbeing):
            title = "Conversation" if obj.kind == "conversation" else "Moment"
            fe = m.FeedEvent(
                user_id=obj.user_id, kind=f"wellbeing_{obj.kind}", severity=obj.severity, title=title,
                body=f"[{obj.mood}] {obj.summary}"[:400],
            )
        else:
            continue
        if obj.created_at is not None:
            fe.created_at = obj.created_at
        session.add(fe)
        session.info.setdefault("feed_users", set()).add(obj.user_id)


@event.listens_for(Session, "after_commit")
def _wake(session: Session) -> None:
    for uid in session.info.pop("feed_users", set()):
        BROKER.notify(uid)


@event.listens_for(Session, "after_rollback")
def _forget(session: Session) -> None:
    session.info.pop("feed_users", None)


class Broker:
    """user id -> waiting sockets. notify() may be called from any thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: dict[int, set[tuple[asyncio.AbstractEventLoop, asyncio.Event]]] = {}

    def subscribe(self, user_id: int) -> asyncio.Event:
        ev = asyncio.Event()
        with self._lock:
            self._subs.setdefault(user_id, set()).add((asyncio.get_running_loop(), ev))
        return ev

    def unsubscribe(self, user_id: int, ev: asyncio.Event) -> None:
        with self._lock:
            subs = self._subs.get(user_id, set())
            for item in [x for x in subs if x[1] is ev]:
                subs.discard(item)

    def notify(self, user_id: int) -> None:
        with self._lock:
            subs = list(self._subs.get(user_id, ()))
        for loop, ev in subs:
            try:
                loop.call_soon_threadsafe(ev.set)
            except RuntimeError:  # loop already closed
                pass

    def count(self, user_id: int) -> int:
        with self._lock:
            return len(self._subs.get(user_id, ()))


BROKER = Broker()


class FeedOut(BaseModel):
    id: int
    kind: str
    severity: str
    title: str
    body: str
    created_at: datetime


def _rows(db: Session, user_id: int, after: int, limit: int = 100) -> list[FeedOut]:
    q = (
        select(m.FeedEvent)
        .where(m.FeedEvent.user_id == user_id, m.FeedEvent.id > after)
        .order_by(m.FeedEvent.id)
        .limit(limit)
    )
    return [
        FeedOut(id=e.id, kind=e.kind, severity=e.severity, title=e.title, body=e.body, created_at=e.created_at)
        for e in db.scalars(q)
    ]


@router.get("/users/{user_id}/feed", response_model=list[FeedOut])
def feed(user_id: int, after: int = 0, limit: int = 100, db: Session = Depends(get_db)) -> list[FeedOut]:
    """REST polling fallback: everything after the last id the client has seen (oldest first)."""
    if after <= 0:  # first load: the newest `limit` rows, oldest first
        last = db.scalars(
            select(m.FeedEvent.id).where(m.FeedEvent.user_id == user_id).order_by(m.FeedEvent.id.desc()).limit(limit)
        ).all()
        after = (min(last) - 1) if last else 0
    return _rows(db, user_id, after, max(1, min(limit, 500)))


RECHECK_S = float(os.environ.get("FEED_RECHECK_S", "5"))


def _ws_key_ok(ws: WebSocket) -> bool:
    expected = os.environ.get("CORE_API_KEY")
    if not expected:
        return testing()
    given = ws.headers.get("x-api-key") or ws.query_params.get("key") or ""
    return hmac.compare_digest(given.encode(), expected.encode())


@ws_router.websocket("/ws/users/{user_id}/feed")
async def feed_socket(ws: WebSocket, user_id: int, after: int = 0, db: Session = Depends(get_db)) -> None:
    """Push: sends {"type":"event", ...} for every new row, {"type":"ping"} when idle. Resume with ?after=<id>."""
    if not _ws_key_ok(ws):
        await ws.close(code=4401)
        return
    await ws.accept()
    ev = BROKER.subscribe(user_id)
    cursor = after
    try:
        while True:
            db.expire_all()
            rows = await asyncio.to_thread(_rows, db, user_id, cursor)
            db.rollback()  # end the read transaction so the next check sees new commits
            for r in rows:
                await ws.send_json({"type": "event", **r.model_dump(mode="json")})
                cursor = r.id
            try:
                await asyncio.wait_for(ev.wait(), timeout=RECHECK_S)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
            ev.clear()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        BROKER.unsubscribe(user_id, ev)
