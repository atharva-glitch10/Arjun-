"""Medicines and doses.

Hard rules (see CLAUDE.md): only the family creates or edits medicines (the endpoints below are the
dashboard's; the propose/confirm path has no medicine-edit action). Name + dose are returned exactly
as entered. "Taken" is self-reported. Not confirmed after N reminders -> family-only notification.
No adherence scores, no streaks.
"""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session

from . import models as m
from . import schemas as s
from .db import get_db
from .deliveries import ack_item, enqueue
from .deps import get_now, require_key

router = APIRouter(dependencies=[Depends(require_key)])

OPEN = ("due", "reminded")


def _user(db: Session, user_id: int) -> m.User:
    user = db.get(m.User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    return user


def _medicine(db: Session, user_id: int, medicine_id: int) -> m.Medicine:
    med = db.get(m.Medicine, medicine_id)
    if med is None or med.user_id != user_id:
        raise HTTPException(404, "medicine not found")
    return med


def due_at_for(user: m.User, med: m.Medicine, day: date) -> datetime:
    """Fixed clock time, or the family-set wake/lunch/dinner time plus the family-set offset."""
    if med.anchor == "fixed":
        hhmm = med.time or "08:00"
        offset = 0
    else:
        hhmm = {"wake": user.wake_time, "lunch": user.lunch_time, "dinner": user.dinner_time}[
            med.anchor
        ]
        offset = med.offset_min
    h, mi = (int(x) for x in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, mi) + timedelta(minutes=offset)


def ensure_doses(db: Session, user: m.User, now: datetime) -> None:
    """Create today's dose rows (idempotent). A medicine added after its time today gets no dose."""
    meds = db.scalars(
        select(m.Medicine).where(m.Medicine.user_id == user.id, m.Medicine.active.is_(True))
    ).all()
    for med in meds:
        exists = db.scalars(
            select(m.MedicineDose).where(
                m.MedicineDose.medicine_id == med.id, m.MedicineDose.for_date == now.date()
            )
        ).first()
        if exists:
            continue
        due = due_at_for(user, med, now.date())
        if due < med.created_at:
            continue
        db.add(
            m.MedicineDose(medicine_id=med.id, user_id=user.id, for_date=now.date(), due_at=due)
        )
    db.flush()


def _out(dose: m.MedicineDose, med: m.Medicine) -> s.DoseOut:
    on_time: bool | None = None
    if dose.taken_at is not None:
        on_time = dose.taken_at <= dose.due_at + timedelta(minutes=med.window_min)
    return s.DoseOut(
        id=dose.id,
        medicine_id=med.id,
        name=med.name,
        dose=med.dose,
        photo_url=med.photo_url,
        anchor=med.anchor,
        due_at=dose.due_at,
        status=dose.status,
        reminders_sent=dose.reminders_sent,
        snoozed_until=dose.snoozed_until,
        taken_at=dose.taken_at,
        on_time=on_time,
    )


def _doses(db: Session, user_id: int, since: datetime) -> list[tuple[m.MedicineDose, m.Medicine]]:
    q = (
        select(m.MedicineDose, m.Medicine)
        .join(m.Medicine, m.Medicine.id == m.MedicineDose.medicine_id)
        .where(m.MedicineDose.user_id == user_id, m.MedicineDose.due_at >= since)
        .order_by(m.MedicineDose.due_at, m.MedicineDose.id)
    )
    return [(d, med) for d, med in db.execute(q).all()]


def open_dose(db: Session, user_id: int, dose_id: int) -> m.MedicineDose:
    dose = db.get(m.MedicineDose, dose_id)
    if dose is None or dose.user_id != user_id:
        raise HTTPException(404, "dose not found")
    if dose.status not in OPEN:
        raise HTTPException(409, f"dose already {dose.status}")
    return dose


def mark_taken(dose: m.MedicineDose, now: datetime) -> None:
    ack_item(object_session(dose), "medicine", dose.id, "taken", now)  # type: ignore[arg-type]
    dose.status = "taken"
    dose.taken_at = now
    dose.snoozed_until = None


def mark_snoozed(dose: m.MedicineDose, now: datetime, minutes: int, max_snoozes: int) -> None:
    if dose.snooze_count >= max_snoozes:
        raise HTTPException(409, "no more snoozes for this dose; family is told if unconfirmed")
    ack_item(object_session(dose), "medicine", dose.id, "snoozed", now)  # type: ignore[arg-type]
    dose.snooze_count += 1
    dose.snoozed_until = now + timedelta(minutes=minutes)


# ---- family: manage medicines ----------------------------------------------------------------
@router.post("/users/{user_id}/medicines", response_model=s.MedicineOut, status_code=201)
def add_medicine(
    user_id: int,
    body: s.MedicineIn,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> m.Medicine:
    _user(db, user_id)
    med = m.Medicine(user_id=user_id, created_at=now, **body.model_dump())
    db.add(med)
    db.commit()
    return med


@router.get("/users/{user_id}/medicines", response_model=list[s.MedicineOut])
def list_medicines(user_id: int, db: Session = Depends(get_db)) -> list[m.Medicine]:
    _user(db, user_id)
    q = select(m.Medicine).where(m.Medicine.user_id == user_id).order_by(m.Medicine.id)
    return list(db.scalars(q))


@router.patch("/users/{user_id}/medicines/{medicine_id}", response_model=s.MedicineOut)
def patch_medicine(
    user_id: int,
    medicine_id: int,
    body: s.MedicinePatch,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> m.Medicine:
    med = _medicine(db, user_id, medicine_id)
    changes = body.model_dump(exclude_unset=True)
    merged = {**s.MedicineIn.model_validate(med, from_attributes=True).model_dump(), **changes}
    try:  # re-validate the combined record (e.g. a fixed anchor still needs a time)
        valid = s.MedicineIn.model_validate(merged)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    for key, value in valid.model_dump().items():
        setattr(med, key, value)
    # An untouched dose for today follows the new schedule.
    stale = db.scalars(
        select(m.MedicineDose).where(
            m.MedicineDose.medicine_id == med.id,
            m.MedicineDose.for_date == now.date(),
            m.MedicineDose.status == "due",
            m.MedicineDose.reminders_sent == 0,
        )
    ).first()
    if stale is not None:
        db.delete(stale)
    db.commit()
    return med


@router.delete("/users/{user_id}/medicines/{medicine_id}", status_code=204)
def delete_medicine(user_id: int, medicine_id: int, db: Session = Depends(get_db)) -> None:
    med = _medicine(db, user_id, medicine_id)
    for dose in db.scalars(select(m.MedicineDose).where(m.MedicineDose.medicine_id == med.id)):
        db.delete(dose)
    db.delete(med)
    db.commit()


@router.get("/users/{user_id}/medicine-doses", response_model=list[s.DoseOut])
def dose_history(
    user_id: int,
    days: int = 7,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> list[s.DoseOut]:
    user = _user(db, user_id)
    ensure_doses(db, user, now)
    db.commit()
    span = max(1, min(days, 31)) - 1
    since = datetime.combine(now.date(), datetime.min.time()) - timedelta(days=span)
    return [_out(d, med) for d, med in _doses(db, user_id, since)]


# ---- elder screen ----------------------------------------------------------------------------
@router.get("/users/{user_id}/medicines/due", response_model=s.DueOut)
def due_now(
    user_id: int, db: Session = Depends(get_db), now: datetime = Depends(get_now)
) -> s.DueOut:
    user = _user(db, user_id)
    ensure_doses(db, user, now)
    db.commit()
    today = datetime.combine(now.date(), datetime.min.time())
    rows = _doses(db, user_id, today)
    current = [
        _out(d, med)
        for d, med in rows
        if d.status in OPEN
        and d.due_at <= now
        and (d.snoozed_until is None or d.snoozed_until <= now)
    ]
    upcoming = [_out(d, med) for d, med in rows if d.status in OPEN and d.due_at > now]
    return s.DueOut(current=current, next=upcoming[0] if upcoming else None)


@router.post("/users/{user_id}/medicine-doses/{dose_id}/taken", response_model=s.DoseOut)
def dose_taken(
    user_id: int,
    dose_id: int,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> s.DoseOut:
    """The elder tapped 'taken' (explicit). Voice goes through propose -> spoken yes instead."""
    dose = open_dose(db, user_id, dose_id)
    med = db.get(m.Medicine, dose.medicine_id)
    assert med is not None
    mark_taken(dose, now)
    db.commit()
    return _out(dose, med)


@router.post("/users/{user_id}/medicine-doses/{dose_id}/snooze", response_model=s.DoseOut)
def dose_snooze(
    user_id: int,
    dose_id: int,
    body: s.SnoozeIn | None = None,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> s.DoseOut:
    dose = open_dose(db, user_id, dose_id)
    med = db.get(m.Medicine, dose.medicine_id)
    assert med is not None
    mark_snoozed(dose, now, (body or s.SnoozeIn()).minutes, med.max_reminders)
    db.commit()
    return _out(dose, med)


# ---- scheduler hook --------------------------------------------------------------------------
@router.post("/internal/medicines/tick")
def tick(
    db: Session = Depends(get_db), now: datetime = Depends(get_now)
) -> dict[str, list[dict[str, object]]]:
    """Called by the scheduler. Returns doses to announce now and doses newly unconfirmed.

    Unconfirmed (max reminders reached, or a previous day) -> ONE family-only notification. The
    elder is never told off and nothing is scored.
    """
    for user in db.scalars(select(m.User)).all():
        ensure_doses(db, user, now)
    reminded: list[dict[str, object]] = []
    unconfirmed: list[dict[str, object]] = []
    open_rows = db.execute(
        select(m.MedicineDose, m.Medicine)
        .join(m.Medicine, m.Medicine.id == m.MedicineDose.medicine_id)
        .where(m.MedicineDose.status.in_(OPEN), m.MedicineDose.due_at <= now)
    ).all()
    for dose, med in open_rows:
        if dose.snoozed_until is not None and dose.snoozed_until > now:
            continue
        gap = timedelta(minutes=med.repeat_minutes)
        if dose.last_reminded_at is not None and now < dose.last_reminded_at + gap:
            continue
        if dose.for_date < now.date() or dose.reminders_sent >= med.max_reminders:
            dose.status = "unconfirmed"
            spoken = (
                db.scalar(
                    select(func.count())
                    .select_from(m.Delivery)
                    .where(m.Delivery.kind == "medicine", m.Delivery.ref_id == dose.id, m.Delivery.spoken_at.is_not(None))
                )
                or 0
            )
            heard = (
                f"none of the {dose.reminders_sent} reminders could be spoken (no elder session was open)"
                if spoken == 0
                else f"{spoken} of {dose.reminders_sent} reminders were spoken"
            )
            db.add(
                m.Notification(
                    user_id=dose.user_id,
                    kind="medicine_unconfirmed",
                    body=(
                        f"{med.name} {med.dose} due {dose.due_at:%H:%M}: not confirmed after "
                        f"{dose.reminders_sent} reminders; {heard}. Arjun cannot tell whether it was taken."
                    )[:300],
                )
            )
            unconfirmed.append({"dose_id": dose.id, "user_id": dose.user_id, "name": med.name})
            continue
        dose.status = "reminded"
        dose.reminders_sent += 1
        dose.last_reminded_at = now
        enqueue(db, dose.user_id, "medicine", dose.id, dose.reminders_sent, now, now)  # T8: wait to be spoken
        reminded.append(
            {
                "dose_id": dose.id,
                "user_id": dose.user_id,
                "name": med.name,
                "dose": med.dose,
                "reminder_no": dose.reminders_sent,
            }
        )
    db.commit()
    return {"reminded": reminded, "unconfirmed": unconfirmed}
