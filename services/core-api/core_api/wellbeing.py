"""How she is doing: seriousness + mood + a short summary per conversation or serious moment. No transcripts.

Written by reasoning (the only service that hears her). Read by the family dashboard. Every row also appears in
the live feed (feed.py). Seriousness: normal < watch < urgent < emergency.
"""

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .db import get_db
from .deps import get_now, require_key

router = APIRouter(dependencies=[Depends(require_key)])

Severity = Literal["normal", "watch", "urgent", "emergency"]
Mood = Literal["happy", "calm", "neutral", "lonely", "sad", "worried", "unwell", "distressed", "not_assessed"]


class WellbeingIn(BaseModel):
    kind: Literal["moment", "conversation"] = "conversation"
    severity: Severity = "normal"
    mood: Mood = "not_assessed"
    summary: str = Field(default="", max_length=400)
    turns: int = Field(default=0, ge=0)
    source: Literal["rules", "llm"] = "rules"
    started_at: datetime | None = None


class WellbeingOut(WellbeingIn):
    id: int
    created_at: datetime


class TodayOut(BaseModel):
    """The dashboard's one-glance answer to 'how is she today?'."""

    severity: Severity
    mood: str
    conversations: int
    last_summary: str
    last_at: datetime | None


def _out(w: m.Wellbeing) -> WellbeingOut:
    return WellbeingOut(
        id=w.id, kind=w.kind, severity=w.severity, mood=w.mood, summary=w.summary, turns=w.turns,  # type: ignore[arg-type]
        source=w.source, started_at=w.started_at, created_at=w.created_at,  # type: ignore[arg-type]
    )


@router.post("/users/{user_id}/wellbeing", response_model=WellbeingOut, status_code=201)
def add(user_id: int, body: WellbeingIn, db: Session = Depends(get_db), now: datetime = Depends(get_now)) -> WellbeingOut:
    if db.get(m.User, user_id) is None:
        raise HTTPException(404, "user not found")
    w = m.Wellbeing(user_id=user_id, created_at=now, **body.model_dump())
    db.add(w)
    db.commit()
    return _out(w)


@router.get("/users/{user_id}/wellbeing", response_model=list[WellbeingOut])
def recent(user_id: int, days: int = 1, db: Session = Depends(get_db), now: datetime = Depends(get_now)) -> list[WellbeingOut]:
    since = datetime.combine(now.date(), datetime.min.time()) - timedelta(days=max(0, days - 1))
    q = select(m.Wellbeing).where(m.Wellbeing.user_id == user_id, m.Wellbeing.created_at >= since)
    return [_out(w) for w in db.scalars(q.order_by(m.Wellbeing.id.desc()))]


_RANK = {"normal": 0, "watch": 1, "urgent": 2, "emergency": 3}


@router.get("/users/{user_id}/wellbeing/today", response_model=TodayOut)
def today(user_id: int, db: Session = Depends(get_db), now: datetime = Depends(get_now)) -> TodayOut:
    rows = recent(user_id, 1, db, now)
    # Seriousness counts EVERY alert of today (an emergency or a help request is a notification, not only a
    # conversation summary), so the headline is never calmer than the alerts below it.
    start = datetime.combine(now.date(), datetime.min.time())
    alert_levels = [
        e.severity for e in db.scalars(
            select(m.FeedEvent).where(m.FeedEvent.user_id == user_id, m.FeedEvent.created_at >= start)
        ) if e.severity in _RANK
    ]
    worst_alert = max(alert_levels, key=_RANK.__getitem__, default="normal")
    if not rows:
        return TodayOut(severity=worst_alert, mood="not_assessed", conversations=0, last_summary="", last_at=None)  # type: ignore[arg-type]
    worst = max(rows, key=lambda w: _RANK[w.severity])
    if _RANK[worst_alert] > _RANK[worst.severity]:
        worst = worst.model_copy(update={"severity": worst_alert})
    convs = [w for w in rows if w.kind == "conversation"]
    assessed = [w for w in rows if w.mood != "not_assessed"]
    return TodayOut(
        severity=worst.severity,
        mood=assessed[0].mood if assessed else "not_assessed",
        conversations=len(convs),
        last_summary=rows[0].summary,
        last_at=rows[0].created_at,
    )
