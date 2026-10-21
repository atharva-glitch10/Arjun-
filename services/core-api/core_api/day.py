"""What time is it, and what is next: one SQL-backed view of today for every client.

The server clock (household timezone) is the single source of time. Reminders, appointments,
medicines and family-set meal times all come from SQL; nothing here is generated.
"""

from datetime import datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from . import schemas as s
from .db import get_db
from .deps import get_now, require_key
from .medicines import ensure_doses

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
    user_id: int, db: Session = Depends(get_db), now: datetime = Depends(get_now)
) -> s.DayOut:
    user = db.get(m.User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    start = datetime.combine(now.date(), time.min)
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
        select(m.Appointment).where(
            m.Appointment.user_id == user_id,
            m.Appointment.starts_at >= start,
            m.Appointment.starts_at < end,
        )
    ):
        items.append(
            s.DayItem(
                kind="appointment",
                at=a.starts_at,
                label=a.title,
                detail=a.location,
                status="scheduled",
                ref_id=a.id,
            )
        )
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
    items.append(s.DayItem(kind="wake", at=_at(now, user.wake_time), label="wake", status="scheduled"))
    items.append(s.DayItem(kind="meal", at=_at(now, user.lunch_time), label="lunch", status="scheduled"))
    items.append(s.DayItem(kind="meal", at=_at(now, user.dinner_time), label="dinner", status="scheduled"))

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
