"""Elder initiated video calls. Telegram only delivers the signed LiveKit join link."""

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import joins, telegram
from . import models as m
from .db import SessionLocal, get_db
from .deps import get_now, local_now, require_key
from .livekit_token import active_room

router = APIRouter(dependencies=[Depends(require_key)])
RING_TIMEOUT = timedelta(seconds=60)
DEDUPE_WINDOW = timedelta(minutes=2)
_timers: dict[int, threading.Timer] = {}
_timer_lock = threading.Lock()

_DOCTOR = ("doctor", "dr.", "डॉक", "वैद्य")


class VideoCallIn(BaseModel):
    contact_id: int
    mode: str = "video"


class VideoCallOut(BaseModel):
    id: int
    user_id: int
    contact_id: int
    contact_name: str
    mode: str
    status: str
    created_at: datetime


def _is_doctor(contact: m.Contact) -> bool:
    rel = (contact.relation or "").casefold()
    return any(word in rel for word in _DOCTOR)


def _out(call: m.VideoCall, contact: m.Contact) -> VideoCallOut:
    return VideoCallOut(
        id=call.id, user_id=call.user_id, contact_id=call.contact_id, contact_name=contact.name,
        mode=call.mode, status=call.status, created_at=call.created_at,
    )


def _mark_missed(db: Session, call: m.VideoCall, current: datetime) -> bool:
    if call.status != "ringing" or current - call.created_at < RING_TIMEOUT:
        return False
    call.status = "missed"
    call.ended_at = current
    contact = db.get(m.Contact, call.contact_id)
    user = db.get(m.User, call.user_id)
    if contact is None or user is None:
        db.commit()
        return True
    elder = user.name.split("(", 1)[0].strip()
    body = f"{elder} यांचा व्हिडिओ कॉल चुकला — परत करा"
    db.add(m.Notification(user_id=call.user_id, kind="video_call_missed", body=body))
    db.commit()
    telegram.send_alert(
        body, joins.join_url(call.user_id), user_id=call.user_id, kind="video_call_missed",
        button_text="परत करा", bind=db.get_bind(),
    )
    return True


def _missed(call_id: int, bind=None, now: datetime | None = None) -> bool:  # type: ignore[no-untyped-def]
    factory = sessionmaker(bind=bind or SessionLocal.kw.get("bind"), autoflush=False, expire_on_commit=False)
    if factory.kw.get("bind") is None:
        return False
    with factory() as db:
        call = db.get(m.VideoCall, call_id)
        current = now or local_now()
        return False if call is None else _mark_missed(db, call, current)


def _schedule_missed(call_id: int, bind) -> None:  # type: ignore[no-untyped-def]
    if os.environ.get("ARJUN_TESTING") == "1":
        return
    def expire() -> None:
        try:
            _missed(call_id, bind)
        finally:
            with _timer_lock:
                _timers.pop(call_id, None)
    timer = threading.Timer(RING_TIMEOUT.total_seconds(), expire)
    timer.daemon = True
    with _timer_lock:
        previous = _timers.pop(call_id, None)
        if previous:
            previous.cancel()
        _timers[call_id] = timer
    timer.start()


def cancel_missed_timer(call_id: int) -> None:
    with _timer_lock:
        timer = _timers.pop(call_id, None)
    if timer is not None:
        timer.cancel()


def expire_ringing_call(call: m.VideoCall, db: Session, now: datetime) -> bool:
    if call.status == "ringing" and now - call.created_at >= RING_TIMEOUT:
        return _mark_missed(db, call, now)
    return False


@router.post("/users/{user_id}/calls", response_model=VideoCallOut, status_code=201)
def start_video_call(
    user_id: int, body: VideoCallIn, db: Session = Depends(get_db), now: datetime = Depends(get_now),
) -> VideoCallOut:
    if body.mode != "video":
        raise HTTPException(422, "only video calls are supported here")
    if active_room(user_id) is None:
        raise HTTPException(409, "the elder's LiveKit room is not open")
    contact = db.get(m.Contact, body.contact_id)
    if contact is None or contact.user_id != user_id or _is_doctor(contact):
        raise HTTPException(422, "choose a family contact")
    prior = db.scalar(select(m.VideoCall).where(
        m.VideoCall.user_id == user_id,
        m.VideoCall.contact_id == contact.id,
        m.VideoCall.status == "ringing",
    ).order_by(m.VideoCall.id.desc()))
    if prior is not None:
        if expire_ringing_call(prior, db, now):
            db.refresh(prior)
        elif now - prior.created_at < DEDUPE_WINDOW:
            return _out(prior, contact)

    active = db.scalar(select(m.VideoCall).where(
        m.VideoCall.user_id == user_id,
        m.VideoCall.status.in_(("ringing", "answered")),
    ).order_by(m.VideoCall.id.desc()))
    if active is not None:
        active_contact = db.get(m.Contact, active.contact_id)
        if active_contact is not None:
            raise HTTPException(409, "a family call is already active")

    call = m.VideoCall(user_id=user_id, contact_id=contact.id, mode="video", status="ringing", created_at=now)
    db.add(call)
    db.commit()
    db.refresh(call)
    user = db.get(m.User, user_id)
    elder = (user.name if user else "आजी").split("(", 1)[0].strip()
    telegram.send_alert(
        f"📹 {elder} व्हिडिओ कॉल करत आहेत", joins.join_url(user_id), user_id=user_id,
        kind=f"video_call:{call.id}", button_text="उचला", bind=db.get_bind(),
    )
    _schedule_missed(call.id, db.get_bind())
    return _out(call, contact)


@router.get("/users/{user_id}/calls/{call_id}", response_model=VideoCallOut)
def video_call_status(
    user_id: int, call_id: int, db: Session = Depends(get_db), now: datetime = Depends(get_now),
) -> VideoCallOut:
    call = db.get(m.VideoCall, call_id)
    if call is None or call.user_id != user_id:
        raise HTTPException(404, "call not found")
    expire_ringing_call(call, db, now)
    db.refresh(call)
    contact = db.get(m.Contact, call.contact_id)
    if contact is None:
        raise HTTPException(404, "contact not found")
    return _out(call, contact)


@router.post("/users/{user_id}/calls/{call_id}/end", response_model=VideoCallOut)
def end_video_call(user_id: int, call_id: int, db: Session = Depends(get_db), now: datetime = Depends(get_now)) -> VideoCallOut:
    call = db.get(m.VideoCall, call_id)
    if call is None or call.user_id != user_id:
        raise HTTPException(404, "call not found")
    if call.status in ("ringing", "answered"):
        call.status = "ended"
        call.ended_at = now
        db.commit()
    contact = db.get(m.Contact, call.contact_id)
    assert contact is not None
    return _out(call, contact)
