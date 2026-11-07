"""Proactive day check-ins: short, warm questions about her day, built only from her own data (checkin_plan.py).

The family turns `daily_checkins` on (and `ARJUN_CHECKINS_ENABLED` is the global switch, default 1). The scheduler's
tick creates today's rows and QUEUES one spoken prompt for each when it comes due. A prompt is a `checkin` delivery
(deliveries.py) exactly like a reminder, so it is spoken by an open voice session and only `spoken_at` means it was
heard.

Rules (all enforced here, in SQL-backed code, never by the LLM):
- inside her opener window (opener_start-opener_end), except an appointment / reminder mention; never 22:00-06:30;
- one question per tick, at least ARJUN_CHECKIN_MIN_GAP_MIN (30) minutes apart; routine care prompts do not count
  against ARJUN_CHECKIN_MAX_PER_DAY (14);
- a topic she already told us today (`volunteer`) is never asked;
- a check-in that waited more than ASK_WINDOW is `missed`: never asked late, never nagged about;
- busy moments (media, a safety flow, a conversation, a reminder being spoken) postpone it 10 minutes, at most 3 times
  (`postpone`, called by reasoning before it claims the prompt), then it is skipped;
- an asked one gets ONE follow-up 20 minutes after the first ask; heard twice and 90 s of silence = `unanswered`;
- her answer (done / skipped) is self-reported and stored as such. No score, no streak, no advice.
"""

import logging
import os
from datetime import datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from . import schemas as s
from .checkin_plan import build_plan, first_name, hm
from .db import get_db
from .deliveries import ack_item, enqueue
from .deps import get_now, require_key
from .medicines import ensure_doses
from .recurrence import occurrence_on

router = APIRouter(dependencies=[Depends(require_key)])
log = logging.getLogger("core_api.checkins")

ASK_WINDOW = timedelta(minutes=90)  # after this a check-in is `missed`; it is never asked late
FOLLOW_UP_AFTER = timedelta(minutes=20)  # exactly one follow-up per check-in
POSTPONE_BY = timedelta(minutes=10)
MAX_POSTPONES = 3
NO_ANSWER_AFTER = timedelta(seconds=90)  # a heard follow-up with this much silence = no answer
QUIET_FROM, QUIET_TO = time(22, 0), time(6, 30)  # nothing is asked in the night, not even a medicine or appointment
HEARD = ("spoken", "shown_only")  # really reached the elder (or the screen), never just queued
EXEMPT_PREFIXES = ("appt", "rem")  # an appointment / reminder mention may leave the opener window
# Routine care prompts are never counted against the daily conversation cap. They still respect the quiet hours,
# one question per tick, and the minimum gap between questions.
ROUTINE_PREFIXES = (
    "sleep", "breakfast", "lunch", "snack", "dinner", "walk", "bp", "sugar", "water", "wellbeing",
    "reflection", "night",
)


def enabled() -> bool:
    return os.environ.get("ARJUN_CHECKINS_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def max_per_day() -> int:
    try:
        return max(0, int(os.environ.get("ARJUN_CHECKIN_MAX_PER_DAY", "14")))
    except ValueError:
        return 14


def min_gap() -> timedelta:
    try:
        return timedelta(minutes=max(0, int(os.environ.get("ARJUN_CHECKIN_MIN_GAP_MIN", "30"))))
    except ValueError:
        return timedelta(minutes=30)


def _user(db: Session, user_id: int) -> m.User:
    user = db.get(m.User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    return user


def is_exempt(kind: str) -> bool:
    return kind.startswith(EXEMPT_PREFIXES)


def is_routine(kind: str) -> bool:
    """Meals, medicines-adjacent checks, BP/sugar, water, walk and the day's wellbeing prompts.

    They are part of her care routine, so they do not use up the daily conversation cap.
    """
    return kind.startswith(ROUTINE_PREFIXES)


def _log_decision(kind: str, decision: str) -> None:
    log.info("checkin %s %s", kind, decision)


def in_quiet_hours(now: datetime) -> bool:
    t = now.time()
    return t >= QUIET_FROM or t < QUIET_TO


def in_window(user: m.User, now: datetime) -> bool:
    return hm(user.opener_start) <= now.time() <= hm(user.opener_end)


def ensure_checkins(db: Session, user: m.User, now: datetime) -> None:
    """Create today's check-in rows (idempotent). Nothing is written when the family (or the global switch) is off."""
    if not user.daily_checkins or not enabled():
        return
    existing = {
        row.kind
        for row in db.scalars(
            select(m.Checkin).where(m.Checkin.user_id == user.id, m.Checkin.for_date == now.date())
        )
    }
    for item in build_plan(db, user, now):
        if item.kind in existing:
            continue
        db.add(
            m.Checkin(user_id=user.id, kind=item.kind, for_date=now.date(), due_at=item.due_at, ref=item.ref)
        )
    db.flush()


def _latest_delivery(db: Session, checkin_id: int) -> m.Delivery | None:
    return db.scalars(
        select(m.Delivery)
        .where(m.Delivery.kind == "checkin", m.Delivery.ref_id == checkin_id)
        .order_by(m.Delivery.id.desc())
    ).first()


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
        ref=c.ref,
        due_at=c.due_at,
        status=c.status,
        asked_at=c.asked_at,
        answered_at=c.answered_at,
        followups=c.followups,
        postponed=c.postponed,
        source=c.source,
        heard=_heard(db, c.id),
    )


def _summary(c: m.Checkin) -> dict[str, object]:
    return {"checkin_id": c.id, "user_id": c.user_id, "kind": c.kind}


def _still_relevant(db: Session, c: m.Checkin, now: datetime) -> bool:
    """An appointment that moved or was deleted, or a reminder already done, is not asked about."""
    if c.kind.startswith("appt"):
        a = db.get(m.Appointment, int(c.kind[4:]))
        when = occurrence_on(a, c.for_date) if a is not None else None
        return when is not None and when > now
    if c.kind.startswith("rem"):
        r = db.get(m.Reminder, int(c.kind[3:]))
        return r is not None and r.status != "done" and r.due_at > now
    return True


def _enqueue(db: Session, c: m.Checkin, ask_no: int, now: datetime) -> None:
    """Attempt number = ask_no (1 first ask, 2 follow-up) + 100 per postponement, so a re-ask is a new queue row."""
    enqueue(db, c.user_id, "checkin", c.id, ask_no + 100 * c.postponed, now, now)


# ---- scheduler hook --------------------------------------------------------------------------
@router.get("/internal/checkin-users")
def checkin_users(db: Session = Depends(get_db)) -> list[int]:
    """The scheduler's fallback when OPENER_USER_IDS / BRIEFING_USER_IDS are empty: everyone with check-ins on."""
    return list(db.scalars(select(m.User.id).where(m.User.daily_checkins.is_(True)).order_by(m.User.id)))


@router.post("/internal/checkins/tick")
def tick(
    db: Session = Depends(get_db), now: datetime = Depends(get_now)
) -> dict[str, list[dict[str, object]]]:
    """Ask the check-in that is due (one per user per tick), one follow-up each, and close what came too late."""
    asked: list[dict[str, object]] = []
    followed_up: list[dict[str, object]] = []
    closed: list[dict[str, object]] = []
    if not enabled():
        return {"asked": asked, "followed_up": followed_up, "closed": closed}
    for user in db.scalars(select(m.User)):
        ensure_checkins(db, user, now)
    for user in db.scalars(select(m.User).where(m.User.daily_checkins.is_(True))):
        rows = list(
            db.scalars(
                select(m.Checkin)
                .where(m.Checkin.user_id == user.id, m.Checkin.for_date == now.date())
                .order_by(m.Checkin.due_at, m.Checkin.id)
            )
        )
        firsts = [c.asked_at for c in rows if c.asked_at is not None]
        nonroutine = [c for c in rows if c.asked_at is not None and not is_routine(c.kind)]
        asked_one = False
        for c in rows:
            if c.status == "pending":
                if c.due_at > now:
                    continue
                if now - c.due_at > ASK_WINDOW:  # hours late: record the truth, never ask it now
                    c.status = "missed"
                    _log_decision(c.kind, "missed")
                    closed.append(_summary(c))
                    continue
                if asked_one or in_quiet_hours(now) or (not is_exempt(c.kind) and not in_window(user, now)):
                    continue  # waits (and ages out) rather than being asked at a wrong moment
                if not is_routine(c.kind) and len(nonroutine) >= max_per_day():
                    c.status = "missed"
                    _log_decision(c.kind, "missed")
                    closed.append(_summary(c))
                    continue
                if firsts and now - max(firsts) < min_gap():
                    continue
                if not _still_relevant(db, c, now):
                    c.status = "missed"
                    _log_decision(c.kind, "missed")
                    closed.append(_summary(c))
                    continue
                c.status = "asked"
                c.asked_at = now
                _enqueue(db, c, 1, now)
                firsts.append(now)
                if not is_routine(c.kind):
                    nonroutine.append(c)
                asked_one = True
                _log_decision(c.kind, "asked")
                asked.append(_summary(c))
                continue
            if c.status != "asked":
                continue
            # asked: close a stale one, otherwise at most one follow-up
            if now - c.due_at > ASK_WINDOW + FOLLOW_UP_AFTER:
                c.status = "unanswered" if _heard(db, c.id) else "missed"
                _log_decision(c.kind, c.status)
                closed.append(_summary(c))
                continue
            if c.followups >= 1:
                last = _latest_delivery(db, c.id)
                if last is not None and last.spoken_at is not None and now - last.spoken_at >= NO_ANSWER_AFTER:
                    c.status = "unanswered"  # asked twice, heard, silence: marked, never a third time
                    _log_decision(c.kind, "missed")
                    closed.append(_summary(c))
                continue
            if (
                c.asked_at is not None
                and now - c.asked_at >= FOLLOW_UP_AFTER
                and not asked_one
                and not in_quiet_hours(now)
                and (is_exempt(c.kind) or in_window(user, now))
                and _still_relevant(db, c, now)
            ):
                for d in db.scalars(
                    select(m.Delivery).where(
                        m.Delivery.kind == "checkin",
                        m.Delivery.ref_id == c.id,
                        m.Delivery.status == "queued",
                    )
                ):
                    d.status, d.outcome = "superseded", "followup"
                c.followups = 1
                _enqueue(db, c, 2, now)
                _log_decision(c.kind, "asked")
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


def _topic_name(c: m.Checkin) -> str:
    """A readable name for the family's one-line note: the kind, or the title for an appointment / reminder."""
    if c.kind.startswith(EXEMPT_PREFIXES):
        return c.ref.split("|", 1)[-1] or c.kind
    return c.kind


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
    c.mood = body.mood or ""
    ack_item(db, "checkin", c.id, body.answer, now)  # finish the queued/spoken prompt
    db.add(
        m.Notification(
            user_id=user_id,
            kind="checkin",
            body=f"{_topic_name(c)} check-in: she said {body.answer} (self-reported).",
        )
    )
    db.commit()
    return _out(db, c)


@router.post("/users/{user_id}/checkins/{checkin_id}/postpone", response_model=s.CheckinOut)
def postpone_checkin(
    user_id: int,
    checkin_id: int,
    reason: str = "",
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> s.CheckinOut:
    """Reasoning calls this when the moment is wrong (media playing, a safety flow, she is mid-conversation, a reminder
    is being spoken). The prompt is taken out of the queue and asked again 10 minutes later, at most 3 times; the 4th
    busy moment skips it. A follow-up that meets a busy moment is simply dropped: never a repeat on top of a repeat."""
    _user(db, user_id)
    c = db.get(m.Checkin, checkin_id)
    if c is None or c.user_id != user_id:
        raise HTTPException(404, "check-in not found")
    if c.status != "asked":
        raise HTTPException(409, f"check-in is {c.status}")
    for d in db.scalars(
        select(m.Delivery).where(
            m.Delivery.kind == "checkin", m.Delivery.ref_id == c.id, m.Delivery.status == "queued"
        )
    ):
        d.status, d.outcome = "superseded", "postponed"
    if c.followups >= 1:
        c.status = "unanswered" if _heard(db, c.id) else "missed"
        _log_decision(c.kind, c.status)
    elif c.postponed >= MAX_POSTPONES:
        c.status = "missed"
        _log_decision(c.kind, "missed")
    else:
        c.postponed += 1
        c.status = "pending"
        c.asked_at = None  # it was not really asked: it counts neither for the daily cap nor the minimum gap
        c.due_at = now + POSTPONE_BY
        _log_decision(c.kind, f"postponed:{reason or 'busy'}")
    db.commit()
    return _out(db, c)


@router.post("/users/{user_id}/checkins/volunteer", response_model=s.CheckinOut | None)
def volunteer_checkin(
    user_id: int,
    body: s.CheckinVolunteer,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> s.CheckinOut | None:
    """She told us on her own ("जेवले"). Today's matching check-in is answered and never asked. Nothing happens when
    the family has check-ins off, or the topic is already settled."""
    user = _user(db, user_id)
    ensure_checkins(db, user, now)
    c = db.scalars(
        select(m.Checkin).where(
            m.Checkin.user_id == user_id, m.Checkin.for_date == now.date(), m.Checkin.kind == body.topic
        )
    ).first()
    if c is None or c.status not in ("pending", "asked"):
        db.commit()
        return None
    c.status, c.answered_at, c.source = body.answer, now, "volunteered"
    ack_item(db, "checkin", c.id, body.answer, now)
    db.commit()
    return _out(db, c)


_STATE = {
    "done": "done", "skipped": "not_done", "unanswered": "no_answer", "missed": "not_asked", "asked": "asking",
}
_DOSE_STATE = {"taken": "done", "not_taken": "not_done", "unconfirmed": "no_answer"}


def _card_kind(kind: str) -> str:
    if kind.startswith("appt"):
        return "appointment"
    if kind.startswith("rem"):
        return "reminder"
    if kind.startswith("water"):
        return "water"
    if kind == "sugar_after":
        return "sugar"
    return kind


def _card_label(c: m.Checkin) -> str:
    if c.kind.startswith(EXEMPT_PREFIXES):
        return c.ref.split("|", 1)[-1]
    if c.kind == "home":
        return first_name(c.ref.split("|", 1)[0])
    if c.kind in ("sugar", "sugar_after"):
        return "fasting" if c.kind == "sugar" else "after_meal"
    return c.ref if c.kind == "interest" else ""


@router.get("/users/{user_id}/checkins/card", response_model=list[s.CheckinCardItem])
def day_card(
    user_id: int, db: Session = Depends(get_db), now: datetime = Depends(get_now)
) -> list[s.CheckinCardItem]:
    """The family's "आजचा दिवस" card: each check-in as done / not done / no answer, with its time. Only what happened.
    No words of hers and no mood here; the mood and summary stay behind the consent flag in the wellbeing card.
    Medicine lines are read from the dose rows the medicine flow already keeps (self-reported, labelled so)."""
    user = _user(db, user_id)
    ensure_checkins(db, user, now)
    ensure_doses(db, user, now)  # today's dose rows, the same way the day view makes them
    db.commit()
    items: list[s.CheckinCardItem] = []
    for c in db.scalars(
        select(m.Checkin).where(m.Checkin.user_id == user_id, m.Checkin.for_date == now.date())
    ):
        state = _STATE.get(c.status, "waiting")
        items.append(
            s.CheckinCardItem(
                kind=_card_kind(c.kind),
                label=_card_label(c),
                at=c.answered_at or (c.asked_at if state != "waiting" else None) or c.due_at,
                state=state,
            )
        )
    for dose, med in db.execute(
        select(m.MedicineDose, m.Medicine)
        .join(m.Medicine, m.Medicine.id == m.MedicineDose.medicine_id)
        .where(m.MedicineDose.user_id == user_id, m.MedicineDose.for_date == now.date())
    ).all():
        items.append(
            s.CheckinCardItem(
                kind="medicine",
                label=med.name,
                at=dose.taken_at or dose.due_at,
                state=_DOSE_STATE.get(dose.status, "waiting"),
            )
        )
    items.sort(key=lambda i: (i.at, i.kind))
    return items


# ---- live demo -------------------------------------------------------------------------------------------------
class DemoFireIn(BaseModel):
    now: str = Field(pattern=r"^\d{2}:\d{2}$")  # the time of day the demo pretends it is
    kind: str | None = None  # fire this kind ("bp", "sugar", "medicine" is not a check-in) instead of the next one


def demo_enabled() -> bool:
    return os.environ.get("ARJUN_CHECKIN_DEMO", "0").strip().lower() in ("1", "true", "yes", "on")


@router.post("/users/{user_id}/checkins/demo-fire")
def demo_fire(
    user_id: int,
    body: DemoFireIn,
    db: Session = Depends(get_db),
    real_now: datetime = Depends(get_now),
) -> dict[str, object]:
    """For a live demo only (ARJUN_CHECKIN_DEMO=1, otherwise 404): ask the NEXT check-in of today's plan right now.

    `now` (HH:MM) is the time of day the demo pretends it is, and it is checked against her window and the quiet
    hours exactly like a real tick. The daily cap and the 30-minute gap are not applied, so the demo can be repeated.
    The prompt is queued at the real time, so a voice session speaks it at once. Nothing else is changed."""
    if not demo_enabled():
        raise HTTPException(404, "not found")
    user = _user(db, user_id)
    if not user.daily_checkins or not enabled():
        return {"fired": None, "reason": "check-ins are switched off for this person"}
    sim = datetime.combine(real_now.date(), hm(body.now))
    ensure_checkins(db, user, sim)
    rows = list(
        db.scalars(
            select(m.Checkin)
            .where(m.Checkin.user_id == user_id, m.Checkin.for_date == real_now.date(), m.Checkin.status == "pending")
            .order_by(m.Checkin.due_at, m.Checkin.id)
        )
    )
    if in_quiet_hours(sim) and body.kind is None:
        db.commit()
        return {"fired": None, "reason": f"{body.now} is inside the quiet hours (22:00-06:30)"}
    for c in rows:
        if body.kind is not None and c.kind != body.kind:
            continue
        if body.kind is None and not is_exempt(c.kind) and not in_window(user, sim):
            continue
        if not _still_relevant(db, c, sim):
            continue
        c.status, c.asked_at, c.due_at = "asked", real_now, real_now
        _enqueue(db, c, 1, real_now)
        _log_decision(c.kind, "asked")
        db.commit()
        return {"fired": c.kind, "checkin_id": c.id, "ref": c.ref}
    db.commit()
    if body.kind is not None:
        return {"fired": None, "reason": f"no pending {body.kind} check-in is left today"}
    return {"fired": None, "reason": f"nothing is left to ask at {body.now} (window {user.opener_start}-{user.opener_end})"}
