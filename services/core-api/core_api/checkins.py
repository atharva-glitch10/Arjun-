"""Family-switched-on meal, walk and BP check-ins.

The family turns `daily_checkins` on; the scheduler's tick creates today's rows at the family-set
times and QUEUES one spoken prompt for each one when it comes due (a meal; the walk and BP check
only when the family put them in her day). A prompt is a `checkin` delivery (deliveries.py) exactly
like a reminder, so it is spoken by an open voice session and only `spoken_at` means it was heard.

Rules:
- a check-in that waited more than ASK_WINDOW is `missed`: never asked late, never nagged about;
- an asked one gets ONE follow-up 30 minutes after the first ask, never a third;
- an ask nobody answered by the end of the window is `unanswered`;
- the elder's spoken answer (done / skipped) is self-reported and stored as such; the family sees
  ONE plain line in the feed. No score, no streak, no advice, no "you should have eaten".
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from . import schemas as s
from .db import get_db
from .deliveries import ack_item, enqueue
from .deps import get_now, require_key

router = APIRouter(dependencies=[Depends(require_key)])

MEALS = ("breakfast", "lunch", "snack")  # dinner is a day marker only for now
OPTIONAL = ("walk", "bp")  # only when the family put them in her day (walk_time / bp_check_time)
ASK_WINDOW = timedelta(minutes=90)  # after this a check-in is `missed`; it is never asked late
FOLLOW_UP_AFTER = timedelta(minutes=30)  # exactly one follow-up per check-in
HEARD = ("spoken", "shown_only")  # really reached the elder (or the screen), never just queued


def _user(db: Session, user_id: int) -> m.User:
    user = db.get(m.User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    return user


def _kind_time(user: m.User, kind: str) -> str:
    return {
        "breakfast": user.breakfast_time,
        "lunch": user.lunch_time,
        "snack": user.snack_time,
        "walk": user.walk_time,
        "bp": user.bp_check_time,
    }[kind] or "00:00"


def _due_at(user: m.User, kind: str, now: datetime) -> datetime:
    h, mi = (int(x) for x in _kind_time(user, kind).split(":"))
    return datetime(now.year, now.month, now.day, h, mi)


def _kinds(user: m.User) -> tuple[str, ...]:
    """The meals always; the walk / BP check only when the family gave them a time."""
    optional = tuple(k for k in OPTIONAL if (user.walk_time if k == "walk" else user.bp_check_time))
    return (*MEALS, *optional)


def ensure_checkins(db: Session, user: m.User, now: datetime) -> None:
    """Create today's check-in rows (idempotent). Nothing is written when the family is off."""
    if not user.daily_checkins:
        return
    existing = {
        row.kind
        for row in db.scalars(
            select(m.Checkin).where(m.Checkin.user_id == user.id, m.Checkin.for_date == now.date())
        )
    }
    for kind in _kinds(user):
        if kind in existing:
            continue
        db.add(
            m.Checkin(
                user_id=user.id,
                kind=kind,
                for_date=now.date(),
                due_at=_due_at(user, kind, now),
            )
        )
    db.flush()


def _heard(db: Session, checkin_id: int) -> bool:
    return (
        db.scalar(
            select(m.Delivery.id)
            .where(
                m.Delivery.kind == "checkin",
                m.Delivery.ref_id == checkin_id,
                (m.Delivery.spoken_at.is_not(None)) | (m.Delivery.status.in_(HEARD)),
            )
            .limit(1)
        )
        is not None
    )


def _out(db: Session, c: m.Checkin) -> s.CheckinOut:
    return s.CheckinOut(
        id=c.id,
        user_id=c.user_id,
        kind=c.kind,
        due_at=c.due_at,
        status=c.status,
        asked_at=c.asked_at,
        answered_at=c.answered_at,
        followups=c.followups,
        heard=_heard(db, c.id),
    )


def _summary(c: m.Checkin) -> dict[str, object]:
    return {"checkin_id": c.id, "user_id": c.user_id, "kind": c.kind}


# ---- scheduler hook --------------------------------------------------------------------------
@router.post("/internal/checkins/tick")
def tick(
    db: Session = Depends(get_db), now: datetime = Depends(get_now)
) -> dict[str, list[dict[str, object]]]:
    """Ask the meals that are due, one follow-up each, and close what came too late."""
    for user in db.scalars(select(m.User)):
        ensure_checkins(db, user, now)
    asked: list[dict[str, object]] = []
    followed_up: list[dict[str, object]] = []
    closed: list[dict[str, object]] = []
    rows = db.scalars(
        select(m.Checkin)
        .where(
            m.Checkin.for_date == now.date(),
            m.Checkin.status.in_(("pending", "asked")),
        )
        .order_by(m.Checkin.due_at, m.Checkin.id)
    )
    for c in rows:
        user = db.get(m.User, c.user_id)
        if user is None or not user.daily_checkins:
            continue
        if c.status == "pending":
            if c.due_at > now:
                continue
            if now - c.due_at > ASK_WINDOW:  # hours late: record the truth, never ask it now
                c.status = "missed"
                closed.append(_summary(c))
                continue
            c.status = "asked"
            c.asked_at = now
            enqueue(db, c.user_id, "checkin", c.id, 1, now, now)
            asked.append(_summary(c))
            continue
        # asked: close a stale one, otherwise at most one 30-minute follow-up
        if now - c.due_at > ASK_WINDOW:
            c.status = "unanswered"
            closed.append(_summary(c))
            continue
        if c.followups == 0 and c.asked_at is not None and now - c.asked_at >= FOLLOW_UP_AFTER:
            for d in db.scalars(
                select(m.Delivery).where(
                    m.Delivery.kind == "checkin",
                    m.Delivery.ref_id == c.id,
                    m.Delivery.status == "queued",
                )
            ):
                d.status, d.outcome = "superseded", "followup"
            c.followups = 1
            enqueue(db, c.user_id, "checkin", c.id, 2, now, now)
            followed_up.append(_summary(c))
    db.commit()
    return {"asked": asked, "followed_up": followed_up, "closed": closed}


# ---- family / elder --------------------------------------------------------------------------
@router.get("/users/{user_id}/checkins", response_model=list[s.CheckinOut])
def list_checkins(
    user_id: int, db: Session = Depends(get_db), now: datetime = Depends(get_now)
) -> list[s.CheckinOut]:
    user = _user(db, user_id)
    ensure_checkins(db, user, now)
    db.commit()
    rows = db.scalars(
        select(m.Checkin).where(m.Checkin.user_id == user_id).order_by(m.Checkin.due_at, m.Checkin.id)
    )
    return [_out(db, c) for c in rows]


@router.get("/users/{user_id}/checkins/open", response_model=s.CheckinOut | None)
def open_checkin(user_id: int, db: Session = Depends(get_db)) -> s.CheckinOut | None:
    """The one meal prompt the elder still has to answer, or None."""
    _user(db, user_id)
    row = db.scalars(
        select(m.Checkin)
        .where(m.Checkin.user_id == user_id, m.Checkin.status == "asked")
        .order_by(m.Checkin.asked_at.desc(), m.Checkin.id.desc())
    ).first()
    return _out(db, row) if row is not None else None


@router.post("/users/{user_id}/checkins/{checkin_id}/answer", response_model=s.CheckinOut)
def answer_checkin(
    user_id: int,
    checkin_id: int,
    body: s.CheckinAnswer,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> s.CheckinOut:
    """Record the elder's own answer. Only an `asked` check-in of this family can be answered."""
    _user(db, user_id)
    c = db.get(m.Checkin, checkin_id)
    if c is None or c.user_id != user_id:
        raise HTTPException(404, "check-in not found")
    if c.status != "asked":
        raise HTTPException(409, f"check-in is {c.status}")
    c.status = body.answer
    c.answered_at = now
    ack_item(db, "checkin", c.id, body.answer, now)  # finish the queued/spoken prompt
    db.add(
        m.Notification(
            user_id=user_id,
            kind="checkin",
            body=f"{c.kind} check-in: she said {body.answer} (self-reported).",
        )
    )
    db.commit()
    return _out(db, c)
