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


def _address_as_default(context) -> str:  # type: ignore[no-untyped-def]
    values = context.get_current_parameters()
    if values.get("age") is not None and values["age"] >= 60:
        return "आजी"
    first = str(values.get("name") or "").split()[0].split("(", 1)[0].strip()
    return f"{first}बाई" if first else "आजी"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    language: Mapped[str] = mapped_column(String(2), default="mr")
    wake_time: Mapped[str] = mapped_column(String(5), default="07:00")
    lunch_time: Mapped[str] = mapped_column(String(5), default="13:00")
    dinner_time: Mapped[str] = mapped_column(String(5), default="20:00")
    # Family-set day markers (task A). walk / BP check are optional: None means "not part of her day".
    breakfast_time: Mapped[str] = mapped_column(String(5), default="08:00")
    snack_time: Mapped[str] = mapped_column(String(5), default="17:00")
    walk_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    bp_check_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    # Meal / walk / BP check-ins are spoken only when the family switched them on.
    daily_checkins: Mapped[bool] = mapped_column(Boolean, default=False)
    honorific: Mapped[str] = mapped_column(String(60), default="")  # how Arjun addresses her ("" = the name)
    address_as: Mapped[str] = mapped_column(String(60), default=_address_as_default, server_default="")  # family editable
    # Read-only context shown to the family (and used by the seed). Never used to give advice or a diagnosis.
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conditions: Mapped[list[str]] = mapped_column(JSON, default=list)
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


class VideoCall(Base):
    __tablename__ = "video_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), index=True)
    mode: Mapped[str] = mapped_column(String(10), default="video")
    status: Mapped[str] = mapped_column(String(10), default="ringing", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


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
    # Optional weekly rule (task B): weekdays 0=Monday..6=Sunday, start/end "HH:MM". `starts_at` is then the first
    # day the rule applies (its time is the default start). None = a one-off appointment.
    weekdays: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    start_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    end_time: Mapped[str | None] = mapped_column(String(5), nullable=True)


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


class Checkin(Base):
    """One family-switched-on meal / walk / BP check-in for one day.

    Only a `daily_checkins` user gets rows. The elder's answer is self-reported: "done" or "skipped".
    Nothing here is scored, summarised or turned into advice. A meal that waited longer than the ask
    window is `missed` and is never asked; an asked one nobody answered goes `unanswered`.
    """

    __tablename__ = "checkins"
    __table_args__ = (UniqueConstraint("user_id", "for_date", "kind", name="uq_checkin_per_day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # sleep | breakfast | lunch | walk | interest | home | dinner | bp | appt<ID> | rem<ID>  (see checkin_plan.py)
    kind: Mapped[str] = mapped_column(String(24))
    for_date: Mapped[date] = mapped_column(Date)
    due_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    # pending | asked | done | skipped | missed | unanswered
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)
    asked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    followups: Mapped[int] = mapped_column(Integer, default=0)  # at most one 20-minute follow-up
    # What the question is about, copied from SQL when the plan is made: "HH:MM|title" (appt, rem), "name|relation"
    # (home), the interest word (interest). Never her words.
    ref: Mapped[str] = mapped_column(String(160), default="")
    postponed: Mapped[int] = mapped_column(Integer, default=0)  # busy moments it waited out (10 min each, max 3)
    mood: Mapped[str] = mapped_column(String(12), default="")  # "" | good | low: one word, never her words
    source: Mapped[str] = mapped_column(String(10), default="asked")  # asked | volunteered (she said it first)


class BpReading(Base):
    """One BP reading the elder read out (voice) or a synthetic device sent. Raw numbers only.

    Boundary 7: no "good / bad / high / low / normal" is stored or derived here, and nothing is scored.
    """

    __tablename__ = "bp_readings"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    systolic: Mapped[int] = mapped_column(Integer)
    diastolic: Mapped[int] = mapped_column(Integer)
    pulse: Mapped[int | None] = mapped_column(Integer, nullable=True)
    measured_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    source: Mapped[str] = mapped_column(String(10), default="voice")  # voice | watch | manual
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WatchSample(Base):
    """One raw sample from the SYNTHETIC watch. No device is paired and no target or alert is derived."""

    __tablename__ = "watch_samples"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # heart_rate | steps | sleep_minutes
    value: Mapped[int] = mapped_column(Integer)
    unit: Mapped[str] = mapped_column(String(10))  # bpm | steps | minutes
    measured_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    source: Mapped[str] = mapped_column(String(20), default="synthetic-watch")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


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
    kind: Mapped[str] = mapped_column(String(10))  # reminder | medicine | checkin
    ref_id: Mapped[int] = mapped_column(Integer)  # reminder id / medicine dose id / check-in id
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


class AppLink(Base):
    """A family-chosen app or link the elder may open by voice (YouTube, news feeds, WhatsApp, a web link)."""

    __tablename__ = "app_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # youtube_query | youtube_video | youtube_playlist | youtube_channel_live | rss | whatsapp | link
    kind: Mapped[str] = mapped_column(String(24))
    label: Mapped[str] = mapped_column(String(100))
    value: Mapped[str] = mapped_column(String(500))  # whatsapp: the CONTACT id (numbers stay in contacts)
    spoken_names: Mapped[list[str]] = mapped_column(JSON, default=list)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    other_host: Mapped[bool] = mapped_column(Boolean, default=False)  # the family approved a host off the allowlist

    @property
    def approved_by_family(self) -> bool:
        """The dashboard's name for `other_host`: an rss/link host outside the known list, approved explicitly."""
        return self.other_host


class YoutubeSearchCache(Base):
    """YouTube search.list costs 100 of the 10,000 daily quota units: results are kept 24 h per normalised query."""

    __tablename__ = "youtube_search_cache"
    query_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    results: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class UserFact(Base):
    """One durable thing Arjun knows about her life ("नातू आर्यन", "she likes bhajans", "Vimal visits on Friday").

    Short wording only: never a transcript, never a number, an address, money, a medicine or a diagnosis (facts.py
    refuses those). Written by reasoning after a conversation (source "auto") or when she says "हे लक्षात ठेव"
    (source "explicit"); the family can delete any row from the dashboard."""

    __tablename__ = "user_facts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    fact: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(12), default="note")  # person|like|dislike|routine|place|event|concern|note
    source_date: Mapped[date] = mapped_column(Date)  # the day she said it (updated when she says it again)
    last_used: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # last time it went into a reply
    confidence: Mapped[float] = mapped_column(default=0.7)
    source: Mapped[str] = mapped_column(String(10), default="auto")  # auto | explicit
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
