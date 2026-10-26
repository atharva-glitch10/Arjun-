"""T8: the delivery queue. A due reminder or medicine prompt is QUEUED here; a voice session CLAIMS it atomically,
speaks it, and only after playback really finished is it marked "spoken". Nothing is silently dropped: items
that are not spoken (too late, over the backlog cap, speech failed) stay listed for the elder screen and the
dashboard with an honest status.

  queued -> speaking (claimed) -> spoken -> acknowledged
  queued -> shown_only    not spoken on purpose (medicine waited past its window; over the backlog cap)
  speaking -> queued      released (interrupted, or TTS failed; 3 TTS failures -> undelivered)
  queued -> superseded    the reminder was done / the dose handled / a newer reminder replaced it

"fired" on a reminder still only means "the due time passed". Only `spoken_at` means Aaji heard it.
"""

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from . import models as m
from .db import get_db
from .deps import get_now, require_key

router = APIRouter(dependencies=[Depends(require_key)])

LATE_AFTER = timedelta(seconds=120)  # a queued item older than this is "not delivered on time"
BACKLOG_CAP = 3  # at most this many LATE items are offered for speech; the rest stay on screen
STALE_CLAIM = timedelta(seconds=90)  # a session that claimed and never finished (crashed)
MAX_TTS_FAILS = 3
OPEN_DOSE = ("due", "reminded")
LIVE = ("queued", "speaking", "spoken", "shown_only", "undelivered")  # not finished, not acknowledged


class DeliveryOut(BaseModel):
    id: int
    kind: str  # reminder | medicine
    ref_id: int
    attempt: int
    due_at: datetime
    status: str
    late: bool
    label: str  # the reminder task / the medicine name, verbatim from SQL
    detail: str  # the medicine dose, verbatim from SQL ("" for reminders)
    spoken_at: datetime | None
    acked_at: datetime | None
    outcome: str | None
    fail_count: int


class SessionIn(BaseModel):
    session: str


class ReleaseIn(SessionIn):
    reason: Literal["tts", "interrupted"] = "interrupted"


class AckIn(BaseModel):
    outcome: str = "ok"


def _user(db: Session, user_id: int) -> m.User:
    user = db.get(m.User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    return user


def _item(db: Session, d: m.Delivery) -> tuple[str, str]:
    if d.kind == "reminder":
        r = db.get(m.Reminder, d.ref_id)
        return (r.task if r else ""), ""
    dose = db.get(m.MedicineDose, d.ref_id)
    med = db.get(m.Medicine, dose.medicine_id) if dose else None
    return (med.name if med else ""), (med.dose if med else "")


def _out(db: Session, d: m.Delivery, now: datetime) -> DeliveryOut:
    label, detail = _item(db, d)
    ended = d.spoken_at or now
    return DeliveryOut(
        id=d.id, kind=d.kind, ref_id=d.ref_id, attempt=d.attempt, due_at=d.due_at, status=d.status,
        late=ended - d.due_at > LATE_AFTER, label=label, detail=detail, spoken_at=d.spoken_at,
        acked_at=d.acked_at, outcome=d.outcome, fail_count=d.fail_count,
    )


def _item_open(db: Session, d: m.Delivery, now: datetime) -> bool:
    """Is the thing this delivery is about still waiting for the elder?"""
    if d.kind == "reminder":
        r = db.get(m.Reminder, d.ref_id)
        return r is not None and r.status != "done"
    dose = db.get(m.MedicineDose, d.ref_id)
    if dose is None or dose.status not in OPEN_DOSE:
        return False
    return dose.snoozed_until is None or dose.snoozed_until <= now


# ---- queueing (called by the scheduler hooks) ----------------------------------------------------------------
def enqueue(db: Session, user_id: int, kind: str, ref_id: int, attempt: int, due_at: datetime, now: datetime) -> bool:
    """Queue a delivery once. A second call for the same (kind, item, attempt) does nothing."""
    exists = db.scalar(
        select(m.Delivery.id).where(
            m.Delivery.kind == kind, m.Delivery.ref_id == ref_id, m.Delivery.attempt == attempt
        )
    )
    if exists:
        return False
    db.add(m.Delivery(user_id=user_id, kind=kind, ref_id=ref_id, attempt=attempt, due_at=due_at, created_at=now))
    return True


def claim_delivery(db: Session, user_id: int, delivery_id: int, session: str, now: datetime) -> bool:
    """Atomic claim: ONE conditional UPDATE decides the winner, so two open sessions can never both speak it."""
    result = db.execute(
        update(m.Delivery)
        .where(m.Delivery.id == delivery_id, m.Delivery.user_id == user_id, m.Delivery.status == "queued")
        .values(status="speaking", claimed_by=session, claimed_at=now)
    )
    db.commit()
    return result.rowcount == 1


def ack_item(db: Session, kind: str, ref_id: int, outcome: str, now: datetime) -> None:
    """The elder dealt with the item (taken / said no / snoozed / reminder done): finish its live deliveries.
    One nobody has heard yet is simply superseded; one that was spoken or shown is acknowledged."""
    for d in db.scalars(
        select(m.Delivery).where(m.Delivery.kind == kind, m.Delivery.ref_id == ref_id, m.Delivery.status.in_(LIVE))
    ):
        d.outcome = outcome
        if d.status == "queued":
            d.status = "superseded"
        else:
            d.status = "acknowledged"
            d.acked_at = now


# ---- the sweep (scheduler tick) -----------------------------------------------------------------------------------
def _notify(db: Session, d: m.Delivery, kind: str, body: str) -> None:
    db.add(m.Notification(user_id=d.user_id, kind=kind, body=body[:300]))
    d.notified = True


def sweep(db: Session, now: datetime) -> dict[str, int]:
    stats = {"released": 0, "superseded": 0, "shown_only": 0, "notified": 0}
    # 1. a session that claimed an item and vanished: put it back (it counts as a failed attempt)
    for d in db.scalars(select(m.Delivery).where(m.Delivery.status == "speaking", m.Delivery.claimed_at < now - STALE_CLAIM)):
        d.fail_count += 1
        d.status = "undelivered" if d.fail_count >= MAX_TTS_FAILS else "queued"
        stats["released"] += 1
    queued = list(db.scalars(select(m.Delivery).where(m.Delivery.status == "queued").order_by(m.Delivery.due_at, m.Delivery.id)))
    # 2. no longer needed
    still: list[m.Delivery] = []
    for d in queued:
        if not _item_open(db, d, now):
            d.status = "superseded"
            stats["superseded"] += 1
        else:
            still.append(d)
    # 2b. a newer reminder for the same dose replaces an older one nobody has heard
    newest: dict[tuple[str, int], m.Delivery] = {}
    for d in still:
        key = (d.kind, d.ref_id)
        if key not in newest or d.attempt > newest[key].attempt:
            newest[key] = d
    still2 = []
    for d in still:
        if d.kind == "medicine" and newest[(d.kind, d.ref_id)] is not d:
            d.status = "superseded"
            stats["superseded"] += 1
        else:
            still2.append(d)
    # 3. a medicine prompt that waited past its on-time window is NOT spoken (never guidance on a missed dose)
    keep: list[m.Delivery] = []
    for d in still2:
        if d.kind == "medicine":
            dose = db.get(m.MedicineDose, d.ref_id)
            med = db.get(m.Medicine, dose.medicine_id) if dose else None
            if med is not None and now - d.due_at > timedelta(minutes=med.window_min):
                d.status = "shown_only"
                stats["shown_only"] += 1
                if not d.notified:
                    _notify(
                        db, d, "medicine_undelivered",
                        f"{med.name} {med.dose} due {d.due_at:%H:%M} was never spoken: no elder session was open. "
                        "It is shown on the screen only. Arjun cannot tell whether it was taken.",
                    )
                    stats["notified"] += 1
                continue
        keep.append(d)
    # 4. backlog cap: of the LATE items per user only the newest few are offered for speech; the rest stay visible
    by_user: dict[int, list[m.Delivery]] = {}
    for d in keep:
        if now - d.due_at > LATE_AFTER:
            by_user.setdefault(d.user_id, []).append(d)
    for items in by_user.values():
        for d in sorted(items, key=lambda x: (x.due_at, x.id))[: max(0, len(items) - BACKLOG_CAP)]:
            d.status = "shown_only"
            stats["shown_only"] += 1
    # 5. tell the family once that a reminder was not spoken on time
    for d in keep:
        if d.status == "queued" and d.kind == "reminder" and not d.notified and now - d.due_at > LATE_AFTER:
            task, _ = _item(db, d)
            _notify(db, d, "undelivered", f"Reminder '{task}' due {d.due_at:%H:%M} was not spoken on time: no elder session was open.")
            stats["notified"] += 1
    db.commit()
    return stats


@router.post("/internal/deliveries/sweep")
def run_sweep(db: Session = Depends(get_db), now: datetime = Depends(get_now)) -> dict[str, int]:
    return sweep(db, now)


# ---- what the voice session and the screens use ----------------------------------------------------------------
@router.get("/users/{user_id}/deliveries/next", response_model=DeliveryOut | None)
def next_delivery(user_id: int, db: Session = Depends(get_db), now: datetime = Depends(get_now)) -> DeliveryOut | None:
    _user(db, user_id)
    for d in db.scalars(
        select(m.Delivery).where(m.Delivery.user_id == user_id, m.Delivery.status == "queued").order_by(m.Delivery.due_at, m.Delivery.id)
    ):
        if _item_open(db, d, now):
            return _out(db, d, now)
        d.status = "superseded"
        db.commit()
    return None


@router.get("/users/{user_id}/deliveries/waiting")
def waiting(user_id: int, db: Session = Depends(get_db)) -> dict[str, int]:
    _user(db, user_id)
    n = db.scalar(select(func.count()).select_from(m.Delivery).where(m.Delivery.user_id == user_id, m.Delivery.status == "queued"))
    return {"queued": int(n or 0)}


@router.get("/users/{user_id}/deliveries/open", response_model=list[DeliveryOut])
def open_deliveries(user_id: int, db: Session = Depends(get_db), now: datetime = Depends(get_now)) -> list[DeliveryOut]:
    """Everything the elder has not dealt with yet, including items that were not spoken. For the elder screen."""
    _user(db, user_id)
    rows = db.scalars(
        select(m.Delivery).where(m.Delivery.user_id == user_id, m.Delivery.status.in_(LIVE)).order_by(m.Delivery.due_at, m.Delivery.id)
    )
    return [_out(db, d, now) for d in rows]


@router.get("/users/{user_id}/deliveries", response_model=list[DeliveryOut])
def list_deliveries(user_id: int, days: int = 1, db: Session = Depends(get_db), now: datetime = Depends(get_now)) -> list[DeliveryOut]:
    """Every delivery of the last `days` days with its true status. For the family dashboard."""
    _user(db, user_id)
    since = now - timedelta(days=days)
    rows = db.scalars(
        select(m.Delivery).where(m.Delivery.user_id == user_id, m.Delivery.due_at >= since).order_by(m.Delivery.due_at, m.Delivery.id)
    )
    return [_out(db, d, now) for d in rows]


def _mine(db: Session, user_id: int, delivery_id: int) -> m.Delivery:
    d = db.get(m.Delivery, delivery_id)
    if d is None or d.user_id != user_id:
        raise HTTPException(404, "delivery not found")
    return d


@router.get("/users/{user_id}/deliveries/{delivery_id}", response_model=DeliveryOut)
def get_delivery(user_id: int, delivery_id: int, db: Session = Depends(get_db), now: datetime = Depends(get_now)) -> DeliveryOut:
    _user(db, user_id)
    return _out(db, _mine(db, user_id, delivery_id), now)


@router.post("/users/{user_id}/deliveries/{delivery_id}/claim", response_model=DeliveryOut)
def claim(user_id: int, delivery_id: int, body: SessionIn, db: Session = Depends(get_db), now: datetime = Depends(get_now)) -> DeliveryOut:
    _user(db, user_id)
    d = _mine(db, user_id, delivery_id)
    if not claim_delivery(db, user_id, delivery_id, body.session, now):
        raise HTTPException(409, "already claimed or no longer waiting")
    db.refresh(d)
    if not _item_open(db, d, now):  # re-checked at claim time: the dose may have been taken a moment ago
        d.status = "superseded"
        db.commit()
        raise HTTPException(409, "no longer needed")
    return _out(db, d, now)


@router.post("/users/{user_id}/deliveries/{delivery_id}/spoken", response_model=DeliveryOut)
def spoken(user_id: int, delivery_id: int, body: SessionIn, db: Session = Depends(get_db), now: datetime = Depends(get_now)) -> DeliveryOut:
    """Call this only AFTER playback finished. Only the session that claimed it can do so."""
    _user(db, user_id)
    d = _mine(db, user_id, delivery_id)
    if d.status != "speaking" or d.claimed_by != body.session:
        raise HTTPException(409, "not claimed by this session")
    d.status, d.spoken_at = "spoken", now
    db.commit()
    return _out(db, d, now)


@router.post("/users/{user_id}/deliveries/{delivery_id}/release", response_model=DeliveryOut)
def release(user_id: int, delivery_id: int, body: ReleaseIn, db: Session = Depends(get_db), now: datetime = Depends(get_now)) -> DeliveryOut:
    """The session could not finish: put the item back. A speech failure counts (3 in a row = undelivered and the
    family is told); being interrupted by the elder does not."""
    _user(db, user_id)
    d = _mine(db, user_id, delivery_id)
    if d.status != "speaking" or d.claimed_by != body.session:
        raise HTTPException(409, "not claimed by this session")
    d.status = "queued"
    if body.reason == "tts":
        d.fail_count += 1
        if d.fail_count >= MAX_TTS_FAILS:
            d.status = "undelivered"
            label, _ = _item(db, d)
            _notify(db, d, "undelivered", f"'{label}' due {d.due_at:%H:%M} could not be spoken: speech failed {d.fail_count} times.")
    db.commit()
    return _out(db, d, now)


@router.post("/users/{user_id}/deliveries/{delivery_id}/ack", response_model=DeliveryOut)
def ack(user_id: int, delivery_id: int, body: AckIn | None = None, db: Session = Depends(get_db), now: datetime = Depends(get_now)) -> DeliveryOut:
    """The elder acknowledged the card (tapped OK)."""
    _user(db, user_id)
    d = _mine(db, user_id, delivery_id)
    d.status, d.acked_at, d.outcome = "acknowledged", now, (body or AckIn()).outcome
    db.commit()
    return _out(db, d, now)
