import os
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from . import schemas as s
from .day import router as day_router
from .db import Base, engine, get_db
from .deliveries import ack_item, enqueue
from .deliveries import router as deliveries_router
from .deps import check_api_key_configured, get_now, require_key
from .livekit_token import router as livekit_router
from .medicines import mark_snoozed, mark_taken, open_dose
from .medicines import router as medicines_router


@asynccontextmanager
async def lifespan(_: FastAPI):  # type: ignore[no-untyped-def]
    check_api_key_configured()  # refuse to start with auth silently disabled
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Arjun core-api", lifespan=lifespan)
router = APIRouter(dependencies=[Depends(require_key)])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _user(db: Session, user_id: int) -> m.User:
    user = db.get(m.User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    return user


# ---- users & contacts -------------------------------------------------------------------------
@router.post("/users", response_model=s.UserOut, status_code=201)
def create_user(body: s.UserIn, db: Session = Depends(get_db)) -> m.User:
    user = m.User(**body.model_dump())
    db.add(user)
    db.commit()
    return user


@router.get("/users/{user_id}", response_model=s.UserOut)
def get_user(user_id: int, db: Session = Depends(get_db)) -> m.User:
    return _user(db, user_id)


@router.patch("/users/{user_id}", response_model=s.UserOut)
def patch_user(user_id: int, body: s.UserPatch, db: Session = Depends(get_db)) -> m.User:
    user = _user(db, user_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(user, key, value)
    db.commit()
    return user


@router.post("/users/{user_id}/contacts", response_model=s.ContactOut, status_code=201)
def add_contact(user_id: int, body: s.ContactIn, db: Session = Depends(get_db)) -> m.Contact:
    _user(db, user_id)
    contact = m.Contact(user_id=user_id, **body.model_dump())
    db.add(contact)
    db.commit()
    return contact


@router.get("/users/{user_id}/contacts", response_model=list[s.ContactOut])
def list_contacts(user_id: int, db: Session = Depends(get_db)) -> list[m.Contact]:
    _user(db, user_id)
    return list(db.scalars(select(m.Contact).where(m.Contact.user_id == user_id)))


# ---- reminders --------------------------------------------------------------------------------
def _check_reminder(body: s.ReminderIn, now: datetime) -> datetime:
    if body.time_ambiguous:
        raise HTTPException(422, "time is ambiguous (AM/PM unclear); ask the user")
    due = datetime.combine(body.date, body.time)
    if due < now - timedelta(minutes=1):
        raise HTTPException(422, "reminder time is in the past")
    return due


@router.post("/users/{user_id}/reminders", response_model=s.ReminderOut, status_code=201)
def create_reminder(
    user_id: int,
    body: s.ReminderIn,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> m.Reminder:
    _user(db, user_id)
    reminder = m.Reminder(user_id=user_id, task=body.task.strip(), due_at=_check_reminder(body, now))
    db.add(reminder)
    db.commit()
    return reminder


@router.get("/users/{user_id}/reminders", response_model=list[s.ReminderOut])
def list_reminders(user_id: int, db: Session = Depends(get_db)) -> list[m.Reminder]:
    _user(db, user_id)
    q = select(m.Reminder).where(m.Reminder.user_id == user_id).order_by(m.Reminder.due_at)
    return list(db.scalars(q))


@router.get("/users/{user_id}/reminders/today", response_model=list[s.ReminderOut])
def reminders_today(
    user_id: int, db: Session = Depends(get_db), now: datetime = Depends(get_now)
) -> list[m.Reminder]:
    _user(db, user_id)
    start = datetime.combine(now.date(), time.min)
    q = (
        select(m.Reminder)
        .where(
            m.Reminder.user_id == user_id,
            m.Reminder.due_at >= start,
            m.Reminder.due_at < start + timedelta(days=1),
        )
        .order_by(m.Reminder.due_at)
    )
    return list(db.scalars(q))


def _complete(db: Session, user_id: int, reminder_id: int) -> m.Reminder:
    reminder = db.get(m.Reminder, reminder_id)
    if reminder is None or reminder.user_id != user_id:
        raise HTTPException(404, "reminder not found")
    reminder.status = "done"
    ack_item(db, "reminder", reminder_id, "done", datetime.now())
    return reminder


@router.post("/users/{user_id}/reminders/{reminder_id}/complete", response_model=s.ReminderOut)
def complete_reminder(user_id: int, reminder_id: int, db: Session = Depends(get_db)) -> m.Reminder:
    reminder = _complete(db, user_id, reminder_id)
    db.commit()
    return reminder


@router.delete("/users/{user_id}/reminders/{reminder_id}", status_code=204)
def delete_reminder(user_id: int, reminder_id: int, db: Session = Depends(get_db)) -> None:
    reminder = db.get(m.Reminder, reminder_id)
    if reminder is None or reminder.user_id != user_id:
        raise HTTPException(404, "reminder not found")
    db.delete(reminder)
    db.commit()


# ---- appointments -----------------------------------------------------------------------------
@router.post("/users/{user_id}/appointments", response_model=s.AppointmentOut, status_code=201)
def add_appointment(
    user_id: int, body: s.AppointmentIn, db: Session = Depends(get_db)
) -> m.Appointment:
    _user(db, user_id)
    appt = m.Appointment(user_id=user_id, **body.model_dump())
    db.add(appt)
    db.commit()
    return appt


@router.get("/users/{user_id}/appointments", response_model=list[s.AppointmentOut])
def list_appointments(user_id: int, db: Session = Depends(get_db)) -> list[m.Appointment]:
    _user(db, user_id)
    q = select(m.Appointment).where(m.Appointment.user_id == user_id)
    return list(db.scalars(q.order_by(m.Appointment.starts_at)))


@router.get("/users/{user_id}/appointments/next", response_model=s.AppointmentOut | None)
def next_appointment(
    user_id: int, db: Session = Depends(get_db), now: datetime = Depends(get_now)
) -> m.Appointment | None:
    _user(db, user_id)
    q = (
        select(m.Appointment)
        .where(m.Appointment.user_id == user_id, m.Appointment.starts_at >= now)
        .order_by(m.Appointment.starts_at)
        .limit(1)
    )
    return db.scalars(q).first()


# ---- stories (private by default) -------------------------------------------------------------
@router.post("/users/{user_id}/stories", response_model=s.StoryOut, status_code=201)
def create_story(user_id: int, body: s.StoryIn, db: Session = Depends(get_db)) -> m.StoryMemory:
    _user(db, user_id)
    story = m.StoryMemory(user_id=user_id, summary=body.summary, share_status="private")
    db.add(story)
    db.commit()
    return story


@router.get("/users/{user_id}/stories/latest", response_model=s.StoryOut | None)
def latest_story(user_id: int, db: Session = Depends(get_db)) -> m.StoryMemory | None:
    """Elder-side only (voice session). Caregiver UI must use /memory-book."""
    _user(db, user_id)
    q = select(m.StoryMemory).where(m.StoryMemory.user_id == user_id)
    return db.scalars(q.order_by(m.StoryMemory.id.desc()).limit(1)).first()


@router.delete("/users/{user_id}/stories/{story_id}", status_code=204)
def forget_story(user_id: int, story_id: int, db: Session = Depends(get_db)) -> None:
    story = db.get(m.StoryMemory, story_id)
    if story is None or story.user_id != user_id:
        raise HTTPException(404, "story not found")
    db.delete(story)
    db.commit()


@router.get("/users/{user_id}/memory-book", response_model=list[s.SharedStoryOut])
def memory_book(user_id: int, db: Session = Depends(get_db)) -> list[m.StoryMemory]:
    """Caregiver view: ONLY stories the user explicitly shared."""
    _user(db, user_id)
    q = select(m.StoryMemory).where(
        m.StoryMemory.user_id == user_id, m.StoryMemory.share_status == "shared"
    )
    return list(db.scalars(q.order_by(m.StoryMemory.id.desc())))


# ---- propose / confirm / reject ---------------------------------------------------------------
def _validate_payload(db: Session, user_id: int, body: s.ProposeIn, now: datetime) -> dict:  # type: ignore[type-arg]
    p = body.payload
    t = body.action_type
    if t == "CREATE_REMINDER":
        rin = s.ReminderIn.model_validate(p)  # missing/invalid slots -> ValidationError
        _check_reminder(rin, now)
        return {"task": rin.task, "date": rin.date.isoformat(), "time": rin.time.strftime("%H:%M")}
    if t == "COMPLETE_REMINDER":
        rid = p.get("reminder_id")
        reminder = db.get(m.Reminder, rid) if isinstance(rid, int) else None
        if reminder is None or reminder.user_id != user_id:
            raise HTTPException(422, "unknown reminder_id")
        return {"reminder_id": rid, "task": reminder.task}
    if t == "REQUEST_CAREGIVER":
        message = str(p.get("message", "")).strip()[:300] or "Please call me."
        return {"message": message}
    if t == "SHARE_STORY":
        sid = p.get("story_id")
        story = db.get(m.StoryMemory, sid) if isinstance(sid, int) else None
        if story is None or story.user_id != user_id:
            raise HTTPException(422, "unknown story_id")
        return {"story_id": sid}
    if t == "SAVE_STORY":
        summary = str(p.get("summary", "")).strip()
        if not summary:
            raise HTTPException(422, "summary required")
        return {"summary": summary[:2000]}
    if t in ("MEDICINE_TAKEN", "MEDICINE_SNOOZE"):
        did = p.get("dose_id")
        if not isinstance(did, int):
            raise HTTPException(422, "unknown dose_id")
        dose = open_dose(db, user_id, did)
        med = db.get(m.Medicine, dose.medicine_id)
        # name/dose are copied verbatim from SQL so the confirmation can quote them exactly
        out = {"dose_id": did, "name": med.name if med else "", "dose": med.dose if med else ""}
        if t == "MEDICINE_TAKEN" and p.get("asked") == "delivery":
            out["asked"] = "delivery"  # the question was "did you take it?", so a no means "not taken"
        return out
    raise HTTPException(422, "unsupported action")  # pragma: no cover


@router.post("/users/{user_id}/actions/propose", response_model=s.PendingOut, status_code=201)
def propose(
    user_id: int,
    body: s.ProposeIn,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> m.PendingAction:
    _user(db, user_id)
    try:
        payload = _validate_payload(db, user_id, body, now)
    except ValueError as exc:  # pydantic ValidationError is a ValueError
        raise HTTPException(422, str(exc)) from exc
    # a new proposal supersedes older unconfirmed ones
    for old in db.scalars(
        select(m.PendingAction).where(
            m.PendingAction.user_id == user_id, m.PendingAction.status == "pending"
        )
    ):
        old.status = "rejected"
    action = m.PendingAction(user_id=user_id, action_type=body.action_type, payload=payload)
    db.add(action)
    db.commit()
    return action


# A yes/no question is answered within seconds. After this long it expires: it must not block the elder
# behind an old question, and a "हो" minutes later must not confirm something asked long ago.
PENDING_TTL = timedelta(seconds=int(os.environ.get("PENDING_TTL_S", "300")))


def _is_stale(action: m.PendingAction, now: datetime) -> bool:
    return now - action.created_at > PENDING_TTL


@router.get("/users/{user_id}/actions/pending", response_model=s.PendingOut | None)
def latest_pending(
    user_id: int, db: Session = Depends(get_db), now: datetime = Depends(get_now)
) -> m.PendingAction | None:
    _user(db, user_id)
    q = select(m.PendingAction).where(
        m.PendingAction.user_id == user_id, m.PendingAction.status == "pending"
    )
    live = None
    for a in db.scalars(q.order_by(m.PendingAction.id.desc())):
        if _is_stale(a, now):
            a.status = "expired"
        elif live is None:
            live = a
    db.commit()
    return live


def _get_pending(db: Session, user_id: int, action_id: int, now: datetime) -> m.PendingAction:
    action = db.get(m.PendingAction, action_id)
    if action is None or action.user_id != user_id:
        raise HTTPException(404, "action not found")
    if action.status == "pending" and _is_stale(action, now):
        action.status = "expired"
        db.commit()
    if action.status != "pending":
        raise HTTPException(409, f"action already {action.status}")
    return action


@router.post("/users/{user_id}/actions/{action_id}/confirm", response_model=s.PendingOut)
def confirm(
    user_id: int,
    action_id: int,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> m.PendingAction:
    action = _get_pending(db, user_id, action_id, now)
    p = action.payload
    if action.action_type == "CREATE_REMINDER":
        due = _check_reminder(
            s.ReminderIn(
                task=p["task"], date=date.fromisoformat(p["date"]), time=time.fromisoformat(p["time"])
            ),
            now,
        )
        db.add(m.Reminder(user_id=user_id, task=p["task"], due_at=due))
    elif action.action_type == "COMPLETE_REMINDER":
        _complete(db, user_id, p["reminder_id"])
    elif action.action_type == "REQUEST_CAREGIVER":
        db.add(m.CaregiverRequest(user_id=user_id, message=p["message"]))
        db.add(m.Notification(user_id=user_id, kind="caregiver_request", body=p["message"]))
    elif action.action_type == "SHARE_STORY":
        story = db.get(m.StoryMemory, p["story_id"])
        if story is None:
            raise HTTPException(404, "story no longer exists")
        story.share_status = "shared"
    elif action.action_type == "SAVE_STORY":
        db.add(m.StoryMemory(user_id=user_id, summary=p["summary"], share_status="private"))
    elif action.action_type in ("MEDICINE_TAKEN", "MEDICINE_SNOOZE"):
        dose = open_dose(db, user_id, p["dose_id"])
        if action.action_type == "MEDICINE_TAKEN":
            mark_taken(dose, now)
        else:
            med = db.get(m.Medicine, dose.medicine_id)
            mark_snoozed(dose, now, 15, med.max_reminders if med else 3)
    action.status = "confirmed"
    db.commit()
    return action


@router.post("/users/{user_id}/actions/{action_id}/reject", response_model=s.PendingOut)
def reject(
    user_id: int,
    action_id: int,
    answer: Literal["no"] | None = None,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> m.PendingAction:
    """`answer=no` means the elder SAID no to this question. For a medicine "taken?" question that is recorded as
    not taken (self-reported) and the family is told, with no advice and no repeat. Any other rejection (a safety
    reply clearing the question, a newer proposal) records nothing about the dose."""
    action = _get_pending(db, user_id, action_id, now)
    action.status = "rejected"
    if answer == "no" and action.action_type == "MEDICINE_TAKEN" and action.payload.get("asked") == "delivery":
        dose = db.get(m.MedicineDose, action.payload.get("dose_id", 0))
        if dose is not None and dose.user_id == user_id and dose.status in ("due", "reminded"):
            med = db.get(m.Medicine, dose.medicine_id)
            dose.status = "not_taken"
            db.add(
                m.Notification(
                    user_id=user_id,
                    kind="medicine_not_taken",
                    body=(
                        f"{med.name} {med.dose} due {dose.due_at:%H:%M}: Aaji said she has not taken it "
                        "(self-reported). Arjun gave no advice."
                    )[:300],
                )
            )
            ack_item(db, "medicine", dose.id, "not_taken", now)
    db.commit()
    return action


@router.get("/users/{user_id}/caregiver-requests")
def caregiver_requests(user_id: int, db: Session = Depends(get_db)) -> list[dict[str, object]]:
    _user(db, user_id)
    q = select(m.CaregiverRequest).where(m.CaregiverRequest.user_id == user_id)
    rows = db.scalars(q.order_by(m.CaregiverRequest.id.desc()))
    return [{"id": r.id, "message": r.message, "created_at": r.created_at} for r in rows]


# ---- safety / companion state -----------------------------------------------------------------
def _emergency_body(user: m.User, contacts: list[m.Contact], now: datetime) -> str:
    """The dashboard alert text. Honest about delivery: it is a dashboard alert only (CLAUDE.md boundary 14)."""
    who = "; ".join(f"{c.name} ({c.relation}) {c.phone}".strip() for c in contacts) or ""
    family = f"Family contacts on file: {who}." if who else "No family contact is set up."
    head = (
        f"EMERGENCY {now:%H:%M}: {user.name} reported a physical emergency (e.g. chest pain, a fall). "
        f"Arjun told her to call 112. Please call her now. "
    )
    tail = " Dashboard alert only; no call or message was sent."
    return (head + family)[: 300 - len(tail)] + tail


@router.post("/users/{user_id}/distress", response_model=s.DistressOut, status_code=201)
def record_distress(
    user_id: int,
    kind: Literal["distress", "emergency"] = "distress",
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> s.DistressOut:
    """Record a safety event and decide whether the family is alerted.

    - emergency (chest pain, can't breathe, a fall, fainting, bleeding): ALWAYS alerts, whatever the consent
      flag says (team decision 2026-10-24). The alert names the configured family contacts.
    - distress (emotional): the caregiver is notified ONLY if the user configured consent. Unchanged.
    """
    user = _user(db, user_id)
    emergency = kind == "emergency"
    alerted = emergency or bool(user.consent_distress_alert)
    db.add(m.DistressEvent(user_id=user_id, caregiver_alerted=alerted))
    if emergency:
        contacts = list(db.scalars(select(m.Contact).where(m.Contact.user_id == user_id).order_by(m.Contact.id)))
        db.add(m.Notification(user_id=user_id, kind="emergency", body=_emergency_body(user, contacts, now)))
    elif alerted:
        db.add(
            m.Notification(
                user_id=user_id,
                kind="distress",
                body="Arjun noticed the user may be upset. Please check in with a call.",
            )
        )
    db.commit()
    return s.DistressOut(caregiver_alerted=alerted)


def _decline_row(db: Session, user_id: int, day: date) -> m.TopicDecline | None:
    return db.scalars(
        select(m.TopicDecline).where(m.TopicDecline.user_id == user_id, m.TopicDecline.day == day)
    ).first()


@router.post("/users/{user_id}/declines", status_code=201)
def record_decline(
    user_id: int, db: Session = Depends(get_db), now: datetime = Depends(get_now)
) -> dict[str, bool]:
    _user(db, user_id)
    row = _decline_row(db, user_id, now.date())
    if row:
        row.count += 1
    else:
        db.add(m.TopicDecline(user_id=user_id, day=now.date()))
    db.commit()
    return {"declined_today": True}


@router.get("/users/{user_id}/opener-allowed")
def opener_allowed(
    user_id: int, db: Session = Depends(get_db), now: datetime = Depends(get_now)
) -> dict[str, bool]:
    """Proactive opener gate: inside caregiver-set hours, not declined today, has interests."""
    user = _user(db, user_id)
    in_hours = user.opener_start <= now.strftime("%H:%M") <= user.opener_end
    declined = _decline_row(db, user_id, now.date()) is not None
    return {"allowed": bool(in_hours and not declined and user.interests)}


@router.get("/users/{user_id}/notifications")
def notifications(user_id: int, db: Session = Depends(get_db)) -> list[dict[str, object]]:
    _user(db, user_id)
    q = select(m.Notification).where(m.Notification.user_id == user_id)
    return [
        {"id": n.id, "kind": n.kind, "body": n.body, "created_at": n.created_at}
        for n in db.scalars(q.order_by(m.Notification.id.desc()))
    ]


# ---- scheduler hook ---------------------------------------------------------------------------
@router.post("/internal/reminders/fire-due")
def fire_due(
    db: Session = Depends(get_db), now: datetime = Depends(get_now)
) -> list[dict[str, object]]:
    due = db.scalars(
        select(m.Reminder).where(m.Reminder.status == "pending", m.Reminder.due_at <= now)
    ).all()
    fired: list[dict[str, object]] = []
    for r in due:
        r.status = "fired"
        r.fired_at = now
        db.add(m.Notification(user_id=r.user_id, kind="reminder", body=r.task))
        enqueue(db, r.user_id, "reminder", r.id, 1, r.due_at, now)  # T8: wait for a voice session to speak it
        fired.append({"reminder_id": r.id, "user_id": r.user_id, "task": r.task})
    db.commit()
    return fired


app.include_router(router)
app.include_router(medicines_router)
app.include_router(day_router)
app.include_router(deliveries_router)
app.include_router(livekit_router)
