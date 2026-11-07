"""Consent-aware, daily-only Marathi summaries sent to family as Gnani voice notes."""

from __future__ import annotations

import logging
import os
import threading
from datetime import date, datetime, time, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from . import telegram
from .db import get_db
from .deps import get_now, require_key

router = APIRouter(dependencies=[Depends(require_key)])
log = logging.getLogger("core_api.briefings")
VOICE_URL = os.environ.get("BRIEFING_VOICE_URL", "http://127.0.0.1:8002/synthesize")
_send_lock = threading.Lock()


class BriefingSendIn(BaseModel):
    force: bool = False


def build_briefing(user_id: int, day: date, db: Session) -> str:
    """Build 3-5 short Marathi sentences using only today's stored facts, never transcripts."""
    user = db.get(m.User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    start, end = datetime.combine(day, time.min), datetime.combine(day + timedelta(days=1), time.min)
    sentences: list[str] = []

    doses = db.scalars(
        select(m.MedicineDose).where(m.MedicineDose.user_id == user_id, m.MedicineDose.for_date == day)
    ).all()
    if doses:
        taken = sum(d.status == "taken" for d in doses)
        missed = sum(d.status in ("unconfirmed", "not_taken") for d in doses)
        sentences.append(f"आज {len(doses)} औषधांच्या नोंदी आहेत; {taken} घेतल्याची नोंद आहे आणि {missed} घेतली नसल्याची किंवा अपूर्ण नोंद आहे.")
    else:
        sentences.append("आज औषधांची नोंद उपलब्ध नाही.")

    readings = db.scalars(
        select(m.BpReading).where(
            m.BpReading.user_id == user_id, m.BpReading.measured_at >= start, m.BpReading.measured_at < end,
        ).order_by(m.BpReading.measured_at.desc(), m.BpReading.id.desc())
    ).all()
    if readings:
        bp = readings[0]
        pulse = f", नाडी {bp.pulse}" if bp.pulse is not None else ""
        sentences.append(f"आजची BP नोंद {bp.systolic}/{bp.diastolic}{pulse} आहे.")
    else:
        sentences.append("आज BP ची नोंद उपलब्ध नाही.")

    meals = db.scalars(
        select(m.Checkin).where(
            m.Checkin.user_id == user_id, m.Checkin.for_date == day,
            m.Checkin.kind.in_(("breakfast", "lunch", "snack", "dinner")),
        ).order_by(m.Checkin.due_at)
    ).all()
    if meals:
        names = {"breakfast": "नाश्ता", "lunch": "दुपारचे जेवण", "snack": "अल्पोपहार", "dinner": "रात्रीचे जेवण"}
        done = [names[c.kind] for c in meals if c.status == "done"]
        other = [names[c.kind] for c in meals if c.status in ("skipped", "missed", "unanswered")]
        detail = []
        if done:
            detail.append("झाल्याची नोंद: " + ", ".join(done))
        if other:
            detail.append("नोंद अपूर्ण: " + ", ".join(other))
        sentences.append("आजच्या जेवणाबद्दल " + ("; ".join(detail) if detail else "नोंदींचे उत्तर आलेले नाही") + ".")
    else:
        sentences.append("आज जेवणाविषयी नोंद उपलब्ध नाही.")

    if user.consent_distress_alert:
        wellbeing = db.scalars(
            select(m.Wellbeing).where(
                m.Wellbeing.user_id == user_id, m.Wellbeing.kind == "conversation",
                m.Wellbeing.created_at >= start, m.Wellbeing.created_at < end,
            ).order_by(m.Wellbeing.created_at.desc(), m.Wellbeing.id.desc())
        ).first()
        if wellbeing and wellbeing.mood != "not_assessed":
            mood = {"happy": "आनंदी", "calm": "शांत", "neutral": "ठीक", "lonely": "एकटेपणा जाणवलेला", "sad": "खिन्न", "worried": "काळजीत", "unwell": "अस्वस्थ", "distressed": "त्रस्त"}.get(wellbeing.mood)
            if mood:
                sentences.append(f"आजच्या नोंदीतील मनःस्थिती: {mood}.")
        if wellbeing and wellbeing.summary.strip():
            # This field is already a short paraphrase, never raw dialogue; consent gates it.
            sentences.append("आजचा ठळक भाग: " + wellbeing.summary.strip().replace("\n", " ").rstrip(".!?।") + ".")

    return " ".join(sentences[:5])


def _send_one_locked(user_id: int, day: date, db: Session, now: datetime, *, force: bool = False) -> str:
    user = db.get(m.User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    if not user.daily_checkins and not force:
        return "disabled"
    text = build_briefing(user_id, day, db)
    record = db.scalars(
        select(m.DailyBriefing).where(m.DailyBriefing.user_id == user_id, m.DailyBriefing.for_date == day)
    ).first()
    if record and not force:
        return "skipped"
    if record is None:
        record = m.DailyBriefing(user_id=user_id, for_date=day, status="pending", attempted_at=now)
        db.add(record)
    else:
        record.status, record.attempted_at = "pending", now
    db.commit()  # reserve today's attempt before any external calls

    ok = False
    try:
        voice_endpoint = httpx.URL(VOICE_URL)
        if voice_endpoint.scheme != "http" or voice_endpoint.host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("briefing voice endpoint must be local HTTP")
        res = httpx.post(
            VOICE_URL, json={"text": text}, headers={"X-API-Key": os.environ.get("CORE_API_KEY", "")}, timeout=45,
        )
        if res.status_code == 200 and res.content:
            ok = telegram.send_voice(res.content, "आजचा सारांश")
        else:
            log.warning("briefing voice synthesis failed user=%s status=%s", user_id, res.status_code)
    except Exception as exc:  # do not log request URLs, text, or response bodies
        log.warning("briefing delivery failed user=%s error=%s", user_id, type(exc).__name__)

    record.status = "sent" if ok else "failed"
    db.add(m.Notification(
        user_id=user_id,
        kind="briefing_sent" if ok else "briefing_failed",
        body="आजचा सारांश Telegram वर पाठवला." if ok else "आजचा सारांश पाठवता आला नाही.",
        created_at=now,
    ))
    db.commit()
    return record.status


def _send_one(user_id: int, day: date, db: Session, now: datetime, *, force: bool = False) -> str:
    # Protect the local single-process API from two simultaneous button/scheduler sends.
    with _send_lock:
        return _send_one_locked(user_id, day, db, now, force=force)


@router.post("/users/{user_id}/briefing/send")
def send_now(
    user_id: int, body: BriefingSendIn, db: Session = Depends(get_db), now: datetime = Depends(get_now),
) -> dict[str, str]:
    status = _send_one(user_id, now.date(), db, now, force=body.force)
    return {"status": status}


@router.post("/internal/briefings/send-due")
def send_due(db: Session = Depends(get_db), now: datetime = Depends(get_now)) -> dict[str, int]:
    hhmm = os.environ.get("BRIEFING_TIME", "20:30")
    try:
        hour, minute = (int(part) for part in hhmm.split(":"))
        scheduled = time(hour, minute)
    except (ValueError, TypeError):
        log.error("invalid BRIEFING_TIME; daily briefings are disabled")
        return {"sent": 0, "failed": 0, "skipped": 0}
    if now.time() < scheduled:
        return {"sent": 0, "failed": 0, "skipped": 0}
    users = db.scalars(select(m.User).where(m.User.daily_checkins.is_(True))).all()
    outcomes = {"sent": 0, "failed": 0, "skipped": 0}
    for user in users:
        try:
            result = _send_one(user.id, now.date(), db, now)
        except Exception as exc:  # one failed user's delivery must not block others
            log.warning("briefing attempt failed user=%s error=%s", user.id, type(exc).__name__)
            result = "failed"
        outcomes["sent" if result == "sent" else "failed" if result == "failed" else "skipped"] += 1
    return outcomes
