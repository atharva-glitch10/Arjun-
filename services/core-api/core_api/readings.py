"""Health readings: raw numbers only, never a judgement (CLAUDE.md boundary 7).

The elder may read a BP reading out loud; the voice path posts the numbers here. A synthetic watch may
post its own samples (Task F). Nothing here says a reading is good, bad, high, low or normal, and no
target or range is stored: the family sees exactly what was measured.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from . import schemas as s
from .db import get_db
from .deps import get_now, require_key

router = APIRouter(dependencies=[Depends(require_key)])


def _user(db: Session, user_id: int) -> m.User:
    user = db.get(m.User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    return user


@router.post("/users/{user_id}/bp-readings", response_model=s.BpReadingOut, status_code=201)
def add_bp_reading(
    user_id: int,
    body: s.BpReadingIn,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> m.BpReading:
    _user(db, user_id)
    reading = m.BpReading(user_id=user_id, measured_at=now, **body.model_dump())
    db.add(reading)
    db.commit()
    return reading


@router.get("/users/{user_id}/bp-readings", response_model=list[s.BpReadingOut])
def list_bp_readings(user_id: int, db: Session = Depends(get_db)) -> list[m.BpReading]:
    """Newest first. Raw values only."""
    _user(db, user_id)
    q = select(m.BpReading).where(m.BpReading.user_id == user_id).order_by(m.BpReading.measured_at.desc(), m.BpReading.id.desc())
    return list(db.scalars(q))
