from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now()  # naive user-local time by design (see README)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    language: Mapped[str] = mapped_column(String(2), default="mr")
    wake_time: Mapped[str] = mapped_column(String(5), default="07:00")
    lunch_time: Mapped[str] = mapped_column(String(5), default="13:00")
    dinner_time: Mapped[str] = mapped_column(String(5), default="20:00")
    interests: Mapped[list[str]] = mapped_column(JSON, default=list)
    opener_start: Mapped[str] = mapped_column(String(5), default="10:00")
    opener_end: Mapped[str] = mapped_column(String(5), default="18:00")
    # Consent: caregiver is alerted on distress only if this is True.
    consent_distress_alert: Mapped[bool] = mapped_column(Boolean, default=False)


class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    relation: Mapped[str] = mapped_column(String(50), default="family")
    phone: Mapped[str] = mapped_column(String(20), default="")  # synthetic numbers only


class Reminder(Base):
    __tablename__ = "reminders"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    task: Mapped[str] = mapped_column(String(200))
    due_at: Mapped[datetime] = mapped_column(DateTime, index=True)  # naive, user-local (IST)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending|fired|done
    fired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    location: Mapped[str] = mapped_column(String(200), default="")


class StoryMemory(Base):
    __tablename__ = "story_memories"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    summary: Mapped[str] = mapped_column(Text)
    share_status: Mapped[str] = mapped_column(String(10), default="private")  # private|shared
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PendingAction(Base):
    __tablename__ = "pending_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSON)  # type: ignore[type-arg]
    status: Mapped[str] = mapped_column(String(10), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CaregiverRequest(Base):
    __tablename__ = "caregiver_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    message: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    body: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DistressEvent(Base):
    """No transcript is stored - only that an event happened and whether a caregiver was alerted."""

    __tablename__ = "distress_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    caregiver_alerted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TopicDecline(Base):
    __tablename__ = "topic_declines"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    day: Mapped[date] = mapped_column(Date)
    count: Mapped[int] = mapped_column(Integer, default=1)


class Medicine(Base):
    """Created and edited by the family only (dashboard). Name and dose are stored exactly as
    entered and are only ever spoken or shown verbatim - never paraphrased or translated."""

    __tablename__ = "medicines"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    dose: Mapped[str] = mapped_column(String(100))
    # fixed = clock time; wake|lunch|dinner = that family-set time + offset_min
    anchor: Mapped[str] = mapped_column(String(10), default="fixed")
    time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    offset_min: Mapped[int] = mapped_column(Integer, default=30)
    max_reminders: Mapped[int] = mapped_column(Integer, default=3)  # then family-only notice
    repeat_minutes: Mapped[int] = mapped_column(Integer, default=15)
    window_min: Mapped[int] = mapped_column(Integer, default=30)  # "on time" window
    photo_url: Mapped[str] = mapped_column(String(500), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MedicineDose(Base):
    """One scheduled intake. `taken` is self-reported by the elder, never verified."""

    __tablename__ = "medicine_doses"
    __table_args__ = (UniqueConstraint("medicine_id", "for_date", name="uq_dose_per_day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    medicine_id: Mapped[int] = mapped_column(ForeignKey("medicines.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    for_date: Mapped[date] = mapped_column(Date)
    due_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    # due | reminded | taken | unconfirmed
    status: Mapped[str] = mapped_column(String(12), default="due")
    reminders_sent: Mapped[int] = mapped_column(Integer, default=0)
    snooze_count: Mapped[int] = mapped_column(Integer, default=0)
    last_reminded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
