"""Family-entered health profile (allergies, doctor, notes) and the day's medicine check.

Everything here is text the family typed, returned verbatim. Arjun never interprets it, never gives advice from it and
the hosted LLM never sees it (CLAUDE.md boundaries 5 and 6). The medicine check lists each dose with what the elder
SELF-REPORTED; it has no score, streak or ranking.
"""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .db import get_db
from .deps import get_now, require_key

router = APIRouter(dependencies=[Depends(require_key)])

MAX_ITEMS = 20


def _clean_list(values: list[str]) -> list[str]:
    seen: list[str] = []
    for v in values:
        v = " ".join(v.split())[:80]
        if v and v.casefold() not in {x.casefold() for x in seen}:
            seen.append(v)
    return seen[:MAX_ITEMS]


class HealthProfileIn(BaseModel):
    allergies: list[str] = Field(default_factory=list, max_length=40)
    conditions: list[str] = Field(default_factory=list, max_length=40)
    blood_group: str = Field(default="", max_length=10)
    doctor_name: str = Field(default="", max_length=100)
    doctor_contact: str = Field(default="", max_length=100)
    prescription_notes: str = Field(default="", max_length=2000)
    emergency_notes: str = Field(default="", max_length=2000)

    @field_validator("allergies", "conditions")
    @classmethod
    def _lists(cls, v: list[str]) -> list[str]:
        return _clean_list(v)

    @field_validator("blood_group", "doctor_name", "doctor_contact", "prescription_notes", "emergency_notes")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class HealthProfileOut(HealthProfileIn):
    updated_at: datetime | None = None


def _user(db: Session, user_id: int) -> m.User:
    user = db.get(m.User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    return user


def _out(user: m.User, row: m.HealthProfile | None) -> HealthProfileOut:
    return HealthProfileOut(
        allergies=list(row.allergies) if row else [],
        conditions=list(user.conditions or []),
        blood_group=row.blood_group if row else "",
        doctor_name=row.doctor_name if row else "",
        doctor_contact=row.doctor_contact if row else "",
        prescription_notes=row.prescription_notes if row else "",
        emergency_notes=row.emergency_notes if row else "",
        updated_at=row.updated_at if row else None,
    )


@router.get("/users/{user_id}/health-profile", response_model=HealthProfileOut)
def get_health_profile(user_id: int, db: Session = Depends(get_db)) -> HealthProfileOut:
    user = _user(db, user_id)
    return _out(user, db.get(m.HealthProfile, user_id))


@router.put("/users/{user_id}/health-profile", response_model=HealthProfileOut)
def put_health_profile(
    user_id: int, body: HealthProfileIn, db: Session = Depends(get_db), now: datetime = Depends(get_now)
) -> HealthProfileOut:
    user = _user(db, user_id)
    row = db.get(m.HealthProfile, user_id)
    if row is None:
        row = m.HealthProfile(user_id=user_id)
        db.add(row)
    row.allergies = body.allergies
    row.blood_group = body.blood_group
    row.doctor_name = body.doctor_name
    row.doctor_contact = body.doctor_contact
    row.prescription_notes = body.prescription_notes
    row.emergency_notes = body.emergency_notes
    row.updated_at = now
    user.conditions = body.conditions
    db.commit()
    return _out(user, row)


class DoseCheck(BaseModel):
    dose_id: int
    medicine_id: int
    name: str  # exactly as the family entered it
    dose: str
    instructions: str
    prescribed_by: str
    due_at: datetime
    taken_at: datetime | None
    status: str
    # on_time | late | pending | overdue | not_confirmed | said_no. Self-reported by the elder, never verified.
    timing: str
    minutes_late: int | None = None
    self_reported: bool = True


def _timing(d: m.MedicineDose, window_min: int, now: datetime) -> tuple[str, int | None]:
    if d.status == "taken" and d.taken_at is not None:
        late = int((d.taken_at - d.due_at).total_seconds() // 60)
        return ("on_time" if late <= window_min else "late"), max(late, 0)
    if d.status == "not_taken":
        return "said_no", None
    if d.status == "unconfirmed":
        return "not_confirmed", None
    if now < d.due_at:
        return "pending", None
    over = int((now - d.due_at).total_seconds() // 60)
    return ("pending" if over <= window_min else "overdue"), None


@router.get("/users/{user_id}/medicine-check", response_model=list[DoseCheck])
def medicine_check(
    user_id: int,
    day: date | None = Query(default=None),
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> list[DoseCheck]:
    """The chosen day's doses (default today) against what the elder reported, for the family. No score, no streak."""
    _user(db, user_id)
    target = day or now.date()
    meds = {x.id: x for x in db.scalars(select(m.Medicine).where(m.Medicine.user_id == user_id))}
    doses = db.scalars(
        select(m.MedicineDose)
        .where(m.MedicineDose.user_id == user_id, m.MedicineDose.for_date == target)
        .order_by(m.MedicineDose.due_at)
    )
    out: list[DoseCheck] = []
    for d in doses:
        med = meds.get(d.medicine_id)
        if med is None:
            continue
        timing, late = _timing(d, med.window_min, now)
        out.append(
            DoseCheck(
                dose_id=d.id, medicine_id=med.id, name=med.name, dose=med.dose, instructions=med.instructions,
                prescribed_by=med.prescribed_by, due_at=d.due_at, taken_at=d.taken_at, status=d.status,
                timing=timing, minutes_late=late,
            )
        )
    return out
