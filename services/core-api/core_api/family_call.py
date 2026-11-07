"""GET /family/join: turn a signed join link into a LiveKit token for the elder's current room.

The family opens the link from Telegram; the web page calls this endpoint (the dev proxy adds the API
key). The signed link is checked here, the elder's most recent room is looked up, and a short-lived
token is issued for identity "family" with the microphone on. The LiveKit secret never leaves the server.
"""

from __future__ import annotations

import os
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from livekit.api import AccessToken, VideoGrants
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import joins
from . import models as m
from .db import get_db
from .deps import local_now, require_key
from .livekit_token import active_room

router = APIRouter(dependencies=[Depends(require_key)])

TOKEN_TTL_S = 3600  # the call itself is not limited by the join link's 30 minutes
FAMILY_IDENTITY = "family"
FALLBACK_NAME = "कुटुंब"
_SON_WORDS = ("son", "मुलगा")
_DOCTOR_WORDS = ("doctor", "डॉक")


def family_name(contacts: list[m.Contact]) -> str:
    """Who the elder's page says is talking: the son, else another family member, never a doctor."""
    for contact in contacts:
        relation = (contact.relation or "").lower()
        if any(word in relation for word in _SON_WORDS):
            return contact.name
    for contact in contacts:
        relation = (contact.relation or "").lower()
        if not any(word in relation for word in _DOCTOR_WORDS):
            return contact.name
    return FALLBACK_NAME


class JoinOut(BaseModel):
    url: str
    token: str
    room: str
    identity: str
    name: str
    expires_in: int
    mode: str = "voice"
    call_id: int | None = None


class CallEndIn(BaseModel):
    t: str


@router.get("/family/join", response_model=JoinOut)
def family_join(t: str = "", db: Session = Depends(get_db)) -> JoinOut:
    signed = joins.claims(t)
    if signed is None:
        raise HTTPException(403, "join link is invalid or expired")
    user_id, call_id = signed
    url = os.environ.get("LIVEKIT_URL")
    key = os.environ.get("LIVEKIT_API_KEY")
    secret = os.environ.get("LIVEKIT_API_SECRET")
    if not (url and key and secret):
        # say nothing about which setting is missing: the caller is a browser
        raise HTTPException(503, "voice is not available")
    user = db.get(m.User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    room = active_room(user_id)
    if room is None:
        raise HTTPException(409, "the elder's voice session is not open")
    contacts = list(
        db.scalars(select(m.Contact).where(m.Contact.user_id == user_id).order_by(m.Contact.id))
    )
    name = family_name(contacts)
    call = db.get(m.VideoCall, call_id) if call_id is not None else db.scalar(select(m.VideoCall).where(
        m.VideoCall.user_id == user_id,
        m.VideoCall.status.in_(("ringing", "answered")),
    ).order_by(m.VideoCall.id.desc()))
    if call_id is not None and (call is None or call.user_id != user_id or call.mode != "video"):
        raise HTTPException(404, "video call not found")
    if call_id is not None and call.status in ("missed", "ended"):
        raise HTTPException(410, "video call has ended")
    if call is not None and call.mode == "video" and call.status == "ringing":
        from .video_calls import expire_ringing_call
        if expire_ringing_call(call, db, local_now()):
            raise HTTPException(410, "video call has expired")
    call = call if call is not None and call.mode == "video" else None
    mode = "video" if call is not None else "voice"
    token = (
        AccessToken(key, secret)
        .with_identity(FAMILY_IDENTITY)
        .with_name(name)
        .with_ttl(timedelta(seconds=min(TOKEN_TTL_S, joins.TTL_S)))
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
                can_publish_sources=["microphone", "camera"] if mode == "video" else ["microphone"],
            )
        )
        .to_jwt()
    )
    return JoinOut(
        url=url,
        token=token,
        room=room,
        identity=FAMILY_IDENTITY,
        name=name,
        expires_in=min(TOKEN_TTL_S, joins.TTL_S),
        mode=mode,
        call_id=call.id if call is not None else None,
    )


@router.post("/family/calls/answer")
def family_call_answer(body: CallEndIn, db: Session = Depends(get_db)) -> dict[str, str]:
    signed = joins.claims(body.t)
    if signed is None:
        raise HTTPException(403, "join link is invalid or expired")
    user_id, call_id = signed
    call = db.get(m.VideoCall, call_id) if call_id is not None else db.scalar(select(m.VideoCall).where(
        m.VideoCall.user_id == user_id,
        m.VideoCall.status.in_(("ringing", "answered")),
    ).order_by(m.VideoCall.id.desc()))
    if call is not None and call.status in ("missed", "ended"):
        raise HTTPException(410, "video call has ended")
    if call is None or call.mode != "video":
        raise HTTPException(409, "there is no ringing video call")
    if call.status == "ringing":
        from .video_calls import cancel_missed_timer, expire_ringing_call
        now = local_now()
        if expire_ringing_call(call, db, now):
            raise HTTPException(410, "video call has expired")
        call.status = "answered"
        call.answered_at = now
        db.commit()
        cancel_missed_timer(call.id)
    return {"status": "answered"}


@router.post("/family/calls/end")
def family_call_end(body: CallEndIn, db: Session = Depends(get_db)) -> dict[str, str]:
    signed = joins.claims(body.t)
    if signed is None:
        raise HTTPException(403, "join link is invalid or expired")
    user_id, call_id = signed
    call = db.get(m.VideoCall, call_id) if call_id is not None else db.scalar(select(m.VideoCall).where(
        m.VideoCall.user_id == user_id,
        m.VideoCall.status.in_(("ringing", "answered")),
    ).order_by(m.VideoCall.id.desc()))
    if call is not None and call.user_id != user_id:
        raise HTTPException(404, "call not found")
    if call is not None:
        call.status = "ended"
        call.ended_at = local_now()
        db.commit()
        if call.mode == "video":
            from .video_calls import cancel_missed_timer
            cancel_missed_timer(call.id)
    return {"status": "ended"}
