"""When did the elder last talk to Arjun or tap the elder screen? One timestamp per user, nothing else.

For the family dashboard's "Last talked to Arjun" line. No words, no transcript and no audio are stored: only
the time and whether it was a spoken turn ("voice") or a tap on the elder screen ("tap"). A new table, so
`create_all` adds it to an existing database without a migration.
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .db import get_db
from .deps import get_now, require_key

router = APIRouter(dependencies=[Depends(require_key)])

How = Literal["voice", "tap"]


class ActivityIn(BaseModel):
    how: How = "voice"


class ActivityOut(BaseModel):
    last_seen_at: datetime | None
    how: str | None


def _row(db: Session, user_id: int) -> m.Activity | None:
    return db.scalars(select(m.Activity).where(m.Activity.user_id == user_id)).first()


def mark_seen(db: Session, user_id: int, now: datetime, how: str) -> None:
    """Record that the elder was active now. The caller commits."""
    row = _row(db, user_id)
    if row is None:
        db.add(m.Activity(user_id=user_id, last_seen_at=now, how=how))
    elif row.last_seen_at is None or now >= row.last_seen_at:
        row.last_seen_at, row.how = now, how


def _user(db: Session, user_id: int) -> None:
    if db.get(m.User, user_id) is None:
        raise HTTPException(404, "user not found")


@router.post("/users/{user_id}/activity", response_model=ActivityOut)
def record_activity(
    user_id: int, body: ActivityIn | None = None, db: Session = Depends(get_db), now: datetime = Depends(get_now)
) -> ActivityOut:
    _user(db, user_id)
    mark_seen(db, user_id, now, (body or ActivityIn()).how)
    db.commit()
    return get_activity(user_id, db)


@router.get("/users/{user_id}/activity", response_model=ActivityOut)
def get_activity(user_id: int, db: Session = Depends(get_db)) -> ActivityOut:
    _user(db, user_id)
    row = _row(db, user_id)
    return ActivityOut(last_seen_at=row.last_seen_at if row else None, how=row.how if row else None)
