"""POST /livekit/token: a short-lived token for one elder voice session (T6).

The LiveKit secret is read from the server's environment and never leaves it: the response holds the
public URL and a signed JWT only. A fresh room name per call matters because agent dispatch happens
when a room is CREATED; reusing a room name would mean no agent on the second session.
"""

import json
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from livekit.api import AccessToken, RoomAgentDispatch, RoomConfiguration, VideoGrants
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import models as m
from .auth import require_livekit_access
from .db import get_db

router = APIRouter()

TOKEN_TTL_S = 600  # only needed to join; LiveKit renews the connection itself afterwards

# The room the elder's page most recently joined, per user. The family-call join link points at it.
# In memory on purpose (single process); a restart forgets it, and the elder's next tap sets it again.
_rooms: dict[int, str] = {}
_rooms_lock = threading.Lock()


def remember_room(user_id: int, room: str) -> None:
    with _rooms_lock:
        _rooms[user_id] = room


def active_room(user_id: int) -> str | None:
    with _rooms_lock:
        return _rooms.get(user_id)


def reset_rooms_for_tests() -> None:
    with _rooms_lock:
        _rooms.clear()


class TokenIn(BaseModel):
    user_id: int
    # the language the elder screen is set to: it travels to the voice agent in the dispatch metadata, and the agent sends it
    # to reasoning with every turn (the frontend owns the language, 2026-11-10)
    language: str | None = Field(default=None, pattern=r"^(mr|hi|en|bn|gu|kn|ml|pa|ta|te|or)$")


class TokenOut(BaseModel):
    url: str
    token: str
    room: str
    identity: str
    expires_in: int


@router.post("/livekit/token", response_model=TokenOut)
def livekit_token(
    body: TokenIn,
    request: Request,
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> TokenOut:
    require_livekit_access(body.user_id, request, x_api_key, db)
    url = os.environ.get("LIVEKIT_URL")
    key = os.environ.get("LIVEKIT_API_KEY")
    secret = os.environ.get("LIVEKIT_API_SECRET")
    if not (url and key and secret):
        # say nothing about which setting is missing: the caller is a browser
        raise HTTPException(503, "voice is not available")
    user = db.get(m.User, body.user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    agent_name = os.environ.get("ARJUN_AGENT_NAME") or "arjun"
    room = f"elder-{user.id}-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{secrets.token_hex(3)}"
    identity = f"elder-{user.id}"
    token = (
        AccessToken(key, secret)
        .with_identity(identity)
        .with_ttl(timedelta(seconds=TOKEN_TTL_S))
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,  # taps travel to the agent as text on the "lk.chat" topic
                can_publish_sources=["microphone", "camera"],
            )
        )
        .with_room_config(RoomConfiguration(
                agents=[RoomAgentDispatch(agent_name=agent_name, metadata=json.dumps({"user_id": user.id, **({"language": body.language} if body.language else {})}))]
            ))
        .to_jwt()
    )
    remember_room(user.id, room)
    return TokenOut(url=url, token=token, room=room, identity=identity, expires_in=TOKEN_TTL_S)
