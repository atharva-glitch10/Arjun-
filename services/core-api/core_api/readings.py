"""Health readings: raw numbers only, never a judgement (CLAUDE.md boundary 7).

The elder may read a BP reading out loud; the voice path posts the numbers here. A synthetic watch may
post its own samples (Task F). Nothing here says a reading is good, bad, high, low or normal, and no
target or range is stored: the family sees exactly what was measured.
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from . import schemas as s
from .db import get_db
from .deps import get_now, require_key

router = APIRouter(dependencies=[Depends(require_key)])

_UNITS = {"heart_rate": "bpm", "steps": "steps", "sleep_minutes": "minutes"}


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


# ---- synthetic watch feed ---------------------------------------------------------------------
@router.post("/users/{user_id}/watch-samples", response_model=s.WatchSampleOut, status_code=201)
def add_watch_sample(
    user_id: int,
    body: s.WatchSampleIn,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> m.WatchSample:
    """One raw sample. The synthetic label is stored; nothing is judged, compared or alerted on."""
    _user(db, user_id)
    sample = m.WatchSample(
        user_id=user_id,
        kind=body.kind,
        value=body.value,
        unit=_UNITS[body.kind],
        measured_at=now,
        source="synthetic-watch",
    )
    db.add(sample)
    db.commit()
    return sample


@router.get("/users/{user_id}/watch-samples", response_model=list[s.WatchSampleOut])
def list_watch_samples(
    user_id: int,
    kind: Literal["heart_rate", "steps", "sleep_minutes"] | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[m.WatchSample]:
    """Newest first, raw. `kind` narrows it to one sample type."""
    _user(db, user_id)
    q = select(m.WatchSample).where(m.WatchSample.user_id == user_id)
    if kind is not None:
        q = q.where(m.WatchSample.kind == kind)
    q = q.order_by(m.WatchSample.measured_at.desc(), m.WatchSample.id.desc()).limit(max(1, min(limit, 500)))
    return list(db.scalars(q))


@router.get("/users/{user_id}/watch-samples/latest", response_model=list[s.WatchSampleOut])
def latest_watch_samples(user_id: int, db: Session = Depends(get_db)) -> list[m.WatchSample]:
    """The newest sample of each kind, in a stable order. Raw values only."""
    _user(db, user_id)
    rows = db.scalars(
        select(m.WatchSample)
        .where(m.WatchSample.user_id == user_id)
        .order_by(m.WatchSample.measured_at.desc(), m.WatchSample.id.desc())
    )
    seen: set[str] = set()
    latest: list[m.WatchSample] = []
    for row in rows:
        if row.kind in seen:
            continue
        seen.add(row.kind)
        latest.append(row)
    return sorted(latest, key=lambda x: x.kind)
