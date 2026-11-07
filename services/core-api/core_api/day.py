"""What time is it, and what is next: one SQL-backed view of today for every client.

The server clock (household timezone) is the single source of time. Reminders, appointments,
medicines and family-set meal times all come from SQL; nothing here is generated.
"""

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from . import schemas as s
from .db import get_db
from .deps import get_now, require_key
from .medicines import due_at_for, ensure_doses
from .recurrence import occurrence_on

router = APIRouter(dependencies=[Depends(require_key)])

CLOSED = {"done", "taken", "unconfirmed"}


def part_of_day(hour: int) -> str:
    if 4 <= hour < 12:
        return "morning"
    if 12 <= hour < 16:
        return "afternoon"
    if 16 <= hour < 19:
        return "evening"
    return "night"


def _at(day: datetime, hhmm: str) -> datetime:
    h, mi = (int(x) for x in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, mi)


@router.get("/users/{user_id}/day", response_model=s.DayOut)
def day_view(
    user_id: int,
    on: date | None = None,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> s.DayOut:
    """Today by default; `on` reads another date. A future day is read-only: no dose rows are created."""
    user = db.get(m.User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    day = on or now.date()
    start = datetime.combine(day, time.min)
    end = start + timedelta(days=1)
    items: list[s.DayItem] = []

    for r in db.scalars(
        select(m.Reminder).where(
            m.Reminder.user_id == user_id, m.Reminder.due_at >= start, m.Reminder.due_at < end
        )
    ):
        items.append(
            s.DayItem(kind="reminder", at=r.due_at, label=r.task, status=r.status, ref_id=r.id)
        )
    for a in db.scalars(
        select(m.Appointment).where(m.Appointment.user_id == user_id)
    ):
        at = occurrence_on(a, day)
        if at is None:
            continue
        items.append(
            s.DayItem(
                kind="appointment",
                at=at,
                label=a.title,
                detail=a.location,
                status="scheduled",
                ref_id=a.id,
            )
        )
    if day == now.date():
        ensure_doses(db, user, now)
        db.commit()
    dose_rows = db.execute(
        select(m.MedicineDose, m.Medicine)
        .join(m.Medicine, m.Medicine.id == m.MedicineDose.medicine_id)
        .where(
            m.MedicineDose.user_id == user_id,
            m.MedicineDose.due_at >= start,
            m.MedicineDose.due_at < end,
        )
    ).all()
    for dose, med in dose_rows:
        items.append(
            s.DayItem(
                kind="medicine",
                at=dose.due_at,
                label=med.name,
                detail=med.dose,
                status=dose.status,
                ref_id=dose.id,
            )
        )
    if day > now.date():  # not generated yet: computed from the family-set schedule, nothing is written
        for med in db.scalars(
            select(m.Medicine).where(m.Medicine.user_id == user_id, m.Medicine.active.is_(True))
        ):
            items.append(
                s.DayItem(
                    kind="medicine",
                    at=due_at_for(user, med, day),
                    label=med.name,
                    detail=med.dose,
                    status="scheduled",
                )
            )
    # Family-set markers (the times are edited on the dashboard); optional ones appear only when the family set them.
    items.append(s.DayItem(kind="wake", at=_at(start, user.wake_time), label="wake", status="scheduled"))
    for label, hhmm in (
        ("breakfast", user.breakfast_time), ("lunch", user.lunch_time), ("snack", user.snack_time),
        ("dinner", user.dinner_time),
    ):
        items.append(s.DayItem(kind="meal", at=_at(start, hhmm), label=label, status="scheduled"))
    if user.walk_time:
        items.append(s.DayItem(kind="walk", at=_at(start, user.walk_time), label="walk", status="scheduled"))
    if user.bp_check_time:
        items.append(s.DayItem(kind="bp", at=_at(start, user.bp_check_time), label="bp", status="scheduled"))
    if user.sugar_check_time:
        items.append(s.DayItem(kind="sugar", at=_at(start, user.sugar_check_time), label="sugar_fasting", status="scheduled"))
    if user.sugar_after_time:
        items.append(s.DayItem(kind="sugar", at=_at(start, user.sugar_after_time), label="sugar_after", status="scheduled"))

    items.sort(key=lambda i: (i.at, i.kind))
    open_now = [
        i
        for i in items
        if i.at <= now and i.status not in CLOSED and i.kind in ("reminder", "medicine")
    ]
    ahead = [i for i in items if i.at > now and i.status not in CLOSED]
    return s.DayOut(
        now=now,
        weekday=now.weekday(),
        part=part_of_day(now.hour),  # type: ignore[arg-type]
        items=items,
        open_now=open_now,
        next=ahead[0] if ahead else None,
    )
