"""POST /livekit/token: a short-lived token for one elder voice session (T6).

The LiveKit secret is read from the server's environment and never leaves it: the response holds the
public URL and a signed JWT only. A fresh room name per call matters because agent dispatch happens
when a room is CREATED; reusing a room name would mean no agent on the second session.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from livekit.api import AccessToken, RoomAgentDispatch, RoomConfiguration, VideoGrants
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import models as m
from .db import get_db
from .deps import require_key

router = APIRouter(dependencies=[Depends(require_key)])

TOKEN_TTL_S = 600  # only needed to join; LiveKit renews the connection itself afterwards


class TokenIn(BaseModel):
    user_id: int


class TokenOut(BaseModel):
    url: str
    token: str
    room: str
    identity: str
    expires_in: int


@router.post("/livekit/token", response_model=TokenOut)
def livekit_token(body: TokenIn, db: Session = Depends(get_db)) -> TokenOut:
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
                can_publish_sources=["microphone"],
            )
        )
        .with_room_config(RoomConfiguration(agents=[RoomAgentDispatch(agent_name=agent_name)]))
        .to_jwt()
    )
    return TokenOut(url=url, token=token, room=room, identity=identity, expires_in=TOKEN_TTL_S)
