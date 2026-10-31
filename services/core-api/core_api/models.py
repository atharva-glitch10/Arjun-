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
from .deps import local_now


def utcnow() -> datetime:
    """Naive HOUSEHOLD-local time (ARJUN_TZ, default Asia/Kolkata), the same clock as `get_now`.

    (Name kept for the existing column defaults.) It used to be the machine clock: in a UTC container a row
    created "now" then looked 5 h 30 min old next to get_now(), so every proposed action expired at once
    (found 2026-10-31 in a smoke run on a UTC machine; on the IST dev laptop the two clocks agreed)."""
    return local_now()


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


class Activity(Base):
    """Last time the elder spoke to Arjun or tapped the elder screen. Time only: no words are stored."""

    __tablename__ = "activity"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    how: Mapped[str] = mapped_column(String(10), default="voice")  # voice | tap


class Wellbeing(Base):
    """How she is doing, for the family: a seriousness level, a mood word and a short summary.

    kind="moment": one serious moment, written at once (help asked, lonely, distress, emergency).
    kind="conversation": one line per finished conversation. NO transcript is stored: the summary is a short
    paraphrase (by the LLM when configured, otherwise built from the intents by rules).
    """

    __tablename__ = "wellbeing"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(15), default="conversation")  # moment | conversation
    severity: Mapped[str] = mapped_column(String(10), default="normal")  # normal | watch | urgent | emergency
    mood: Mapped[str] = mapped_column(String(20), default="not_assessed")
    summary: Mapped[str] = mapped_column(String(400), default="")
    turns: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(10), default="rules")  # rules | llm
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FeedEvent(Base):
    """One line of the family's live feed (WebSocket push + REST polling share this table and its ids).

    Written automatically for every new Notification and Wellbeing row (see feed.py), so no endpoint can forget.
    """

    __tablename__ = "feed_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    severity: Mapped[str] = mapped_column(String(10), default="info")  # info | normal | watch | urgent | emergency
    title: Mapped[str] = mapped_column(String(120), default="")
    body: Mapped[str] = mapped_column(String(400), default="")
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


class Delivery(Base):
    """One due reminder / medicine prompt on its way to the elder's voice session (T8). See deliveries.py."""

    __tablename__ = "deliveries"
    __table_args__ = (UniqueConstraint("kind", "ref_id", "attempt", name="uq_delivery_once"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # reminder | medicine
    ref_id: Mapped[int] = mapped_column(Integer)  # reminder id / medicine dose id
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    due_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    # queued | speaking | spoken | acknowledged | shown_only | undelivered | superseded
    status: Mapped[str] = mapped_column(String(14), default="queued", index=True)
    claimed_by: Mapped[str | None] = mapped_column(String(60), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    spoken_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # set only after playback finished
    acked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(14), nullable=True)  # taken | not_taken | snoozed | done | ok
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)  # the family was told it was not delivered
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
    # due | reminded | taken | unconfirmed | not_taken (the elder said no; self-reported)
    status: Mapped[str] = mapped_column(String(12), default="due")
    reminders_sent: Mapped[int] = mapped_column(Integer, default=0)
    snooze_count: Mapped[int] = mapped_column(Integer, default=0)
    last_reminded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
