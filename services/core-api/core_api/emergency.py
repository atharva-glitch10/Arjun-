"""Emergency escalation (team decision 2026-11-08, replaces "dashboard alert only" for physical emergencies).

When reasoning records a physical emergency the family already gets the dashboard alarm + Telegram (main.py). The
voice-agent then calls `/internal/users/{id}/emergency/escalate`:
  stage "family": phone the family contacts that have a number (max 2);
  stage "help":   if she has not answered within ARJUN_EMERGENCY_WAIT_S, phone the family-chosen help number
                  (nurse desk / warden / nearby hospital / private ambulance) and read the saved address.
Arjun NEVER dials 112 or any number the family did not save. Calls use Twilio only when CALLS_ENABLED=1; every
attempt is recorded with its real outcome (boundary 14), and the dashboard shows it.

Live location: the elder device posts its position when the emergency screen opens. It is kept ONLY if a physical
emergency was recorded in the last LOCATION_WINDOW (otherwise discarded, e.g. emotional distress), and the family
gets it on Telegram as a Google Maps button. No continuous tracking.
"""

import os
import re
import threading
from datetime import timedelta
from xml.sax.saxutils import escape

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from . import telegram
from .db import get_db
from .deps import get_now, require_key

router = APIRouter(dependencies=[Depends(require_key)])

LOCATION_WINDOW = timedelta(minutes=15)
ESCALATE_DEDUPE = timedelta(minutes=10)
_lock = threading.Lock()


class SettingsIn(BaseModel):
    help_label: str = Field(default="", max_length=80)
    help_phone: str = Field(default="", max_length=20)
    address: str = Field(default="", max_length=300)
    call_family: bool = True


class LocationIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: float = Field(default=0.0, ge=0, le=100000)


class EscalateIn(BaseModel):
    stage: str = Field(pattern="^(family|help)$")


def calls_enabled() -> bool:
    return os.environ.get("CALLS_ENABLED", "0").strip() == "1"


def e164(phone: str) -> str:
    """Indian numbers as +91XXXXXXXXXX; anything already starting with + kept. '' if it is not a phone number."""
    digits = re.sub(r"[^\d+]", "", phone or "")
    if digits.startswith("+") and len(digits) >= 9:
        return digits
    digits = digits.lstrip("+")
    if digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10:
        return "+91" + digits
    if len(digits) == 12 and digits.startswith("91"):
        return "+" + digits
    return ""


def twiml(message: str) -> str:
    said = escape(message)
    return (
        f'<Response><Say language="hi-IN">{said}</Say><Pause length="1"/>'
        f'<Say language="hi-IN">{said}</Say></Response>'
    )


def place_call(to: str, message: str) -> tuple[str, str]:
    """Twilio voice call reading `message`. Returns (status, detail). Replaced in tests (no network)."""
    if not calls_enabled():
        return "skipped_disabled", "CALLS_ENABLED is not 1"
    sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    from_ = os.environ.get("TWILIO_FROM", "").strip()
    if not (sid and token and from_) or "X" in from_:
        return "failed", "Twilio is not configured (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM)"
    try:
        res = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json",
            auth=(sid, token),
            data={"To": to, "From": from_, "Twiml": twiml(message)},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        return "failed", f"Twilio unreachable ({type(exc).__name__})"
    if res.status_code in (200, 201):
        return "placed", ""
    try:
        reason = str(res.json().get("message", ""))[:150]
    except ValueError:
        reason = ""
    return "failed", f"Twilio {res.status_code}: {reason}"


def _name(user: m.User) -> str:
    return re.sub(r"\s*\([^)]*\)", "", user.name or "").strip() or "Arjun user"


def _settings(db: Session, user_id: int) -> m.EmergencySettings:
    row = db.get(m.EmergencySettings, user_id)
    return row or m.EmergencySettings(user_id=user_id)


def _recent_emergency(db: Session, user_id: int, now) -> bool:  # type: ignore[no-untyped-def]
    return db.scalar(
        select(m.Notification.id).where(
            m.Notification.user_id == user_id, m.Notification.kind == "emergency",
            m.Notification.created_at >= now - LOCATION_WINDOW,
        )
    ) is not None


def maps_url(lat: float, lon: float) -> str:
    return f"https://maps.google.com/?q={lat:.6f},{lon:.6f}"


@router.get("/users/{user_id}/emergency-settings")
def get_settings(user_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    s = _settings(db, user_id)
    return {"help_label": s.help_label or "", "help_phone": s.help_phone or "", "address": s.address or "",
            "call_family": s.call_family if s.call_family is not None else True, "calls_enabled": calls_enabled()}


@router.put("/users/{user_id}/emergency-settings")
def put_settings(user_id: int, body: SettingsIn, db: Session = Depends(get_db)) -> dict[str, object]:
    if db.get(m.User, user_id) is None:
        raise HTTPException(404, "user not found")
    if body.help_phone.strip() and not e164(body.help_phone):
        raise HTTPException(422, "help number must be a 10-digit Indian number or +country format")
    row = db.get(m.EmergencySettings, user_id) or m.EmergencySettings(user_id=user_id)
    row.help_label, row.help_phone = body.help_label.strip(), body.help_phone.strip()
    row.address, row.call_family = body.address.strip(), body.call_family
    db.add(row)
    db.commit()
    return get_settings(user_id, db)


@router.post("/users/{user_id}/emergency/location")
def post_location(user_id: int, body: LocationIn, db: Session = Depends(get_db), now=Depends(get_now)):  # type: ignore[no-untyped-def]
    """Kept and shared ONLY during an active physical emergency; otherwise discarded."""
    user = db.get(m.User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    if not _recent_emergency(db, user_id, now):
        return {"kept": False}
    db.add(m.EmergencyLocation(user_id=user_id, lat=body.lat, lon=body.lon, accuracy_m=body.accuracy_m, at=now))
    url = maps_url(body.lat, body.lon)
    db.add(m.Notification(user_id=user_id, kind="emergency",
                          body=f"Live location of {_name(user)} at {now:%H:%M} (±{int(body.accuracy_m)} m): {url}"))
    db.commit()
    if telegram.claim(user_id, "emergency_location") == "ready":
        telegram.send_alert(
            f"📍 Live location of {_name(user)} ({now:%H:%M}, about ±{int(body.accuracy_m)} m)",
            url, user_id=user_id, kind="emergency_location", bind=db.get_bind(), button_text="📍 Open live location",
        )
    return {"kept": True, "maps_url": url}


def _latest_location(db: Session, user_id: int, now) -> m.EmergencyLocation | None:  # type: ignore[no-untyped-def]
    return db.scalar(
        select(m.EmergencyLocation).where(
            m.EmergencyLocation.user_id == user_id, m.EmergencyLocation.at >= now - LOCATION_WINDOW
        ).order_by(m.EmergencyLocation.id.desc())
    )


@router.post("/internal/users/{user_id}/emergency/escalate")
def escalate(user_id: int, body: EscalateIn, db: Session = Depends(get_db), now=Depends(get_now)):  # type: ignore[no-untyped-def]
    """Service-only (voice-agent). Places the calls for one stage, at most once per stage per 10 minutes."""
    user = db.get(m.User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    with _lock:
        recent = db.scalar(
            select(m.EmergencyCall.id).where(
                m.EmergencyCall.user_id == user_id, m.EmergencyCall.stage == body.stage,
                m.EmergencyCall.at >= now - ESCALATE_DEDUPE,
            )
        )
        if recent is not None:
            return {"stage": body.stage, "placed": 0, "deduped": True, "calls": []}
        cfg = _settings(db, user_id)
        name = _name(user)
        loc = _latest_location(db, user_id, now)
        targets: list[tuple[str, str]] = []
        if body.stage == "family":
            if cfg.call_family is not False:
                contacts = db.scalars(select(m.Contact).where(m.Contact.user_id == user_id).order_by(m.Contact.id))
                targets = [(f"{c.name} ({c.relation})", c.phone) for c in contacts if e164(c.phone)][:2]
            message = (f"Arjun emergency alert. {name} ne abhi bataya ki unhe takleef hai, jaise seene mein dard ya "
                       f"girna. Kripya unhe turant phone kijiye. Location Telegram par bheji gayi hai.")
        else:
            if cfg.help_phone:
                targets = [(cfg.help_label or "Help number", cfg.help_phone)]
            where = cfg.address or "address not saved"
            message = (f"Arjun automatic emergency alert. {name} ko turant madad chahiye ho sakti hai. "
                       f"Pata: {where}. Unhone 10 second tak jawab nahi diya. Parivar ko suchit kar diya gaya hai.")
        calls = []
        if not targets:
            db.add(m.EmergencyCall(user_id=user_id, stage=body.stage, target="-", status="skipped_no_number",
                                   detail="no phone number saved for this stage", at=now))
        for label, phone in targets:
            status, detail = place_call(e164(phone), message)
            tail = re.sub(r"\D", "", phone)[-4:]
            db.add(m.EmergencyCall(user_id=user_id, stage=body.stage, target=label, phone_tail=tail,
                                   status=status, detail=detail, at=now))
            calls.append({"target": label, "status": status})
        placed = sum(1 for c in calls if c["status"] == "placed")
        if body.stage == "help":
            outcome = (f"called {targets[0][0]}" if placed else
                       ("no help number saved" if not targets else f"call to {targets[0][0]} NOT placed"))
            link = f" Location: {maps_url(loc.lat, loc.lon)}" if loc else ""
            db.add(m.Notification(user_id=user_id, kind="emergency",
                                  body=f"NO ANSWER from {name} for 10 s after the emergency ({now:%H:%M}): {outcome}.{link}"))
        db.commit()
    if body.stage == "help" and telegram.claim(user_id, "emergency_noanswer") == "ready":
        url = maps_url(loc.lat, loc.lon) if loc else None
        telegram.send_alert(
            f"🚨 NO ANSWER from {name} for 10 seconds after the emergency. "
            + (f"Arjun phoned {targets[0][0]}. " if placed else "No help call was placed. ")
            + "Call her or 112 now.",
            url, user_id=user_id, kind="emergency_noanswer", bind=db.get_bind(),
            button_text="📍 Open live location" if url else None,
        )
    return {"stage": body.stage, "placed": placed, "deduped": False, "calls": calls}


@router.get("/users/{user_id}/emergency/calls")
def recent_calls(user_id: int, db: Session = Depends(get_db), now=Depends(get_now)) -> list[dict[str, object]]:
    rows = db.scalars(
        select(m.EmergencyCall).where(m.EmergencyCall.user_id == user_id, m.EmergencyCall.at >= now - timedelta(days=1))
        .order_by(m.EmergencyCall.id.desc()).limit(20)
    )
    return [{"stage": r.stage, "target": r.target, "phone_tail": r.phone_tail, "status": r.status,
             "detail": r.detail, "at": r.at} for r in rows]
