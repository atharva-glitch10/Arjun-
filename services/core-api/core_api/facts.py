"""What Arjun knows about her life: short facts, one row each (the "long-term memory").

reasoning PROPOSES facts (extracted after a conversation, or "हे लक्षात ठेव"); this module VALIDATES and stores them
(boundary 1: the LLM never touches the database). The never-store rules live here, once:

  * no numbers of any kind (phone, age, dates as digits, doses), no money, no addresses;
  * no medicines, no diagnoses (boundaries 5 and 6);
  * a "concern" (a body complaint worded without a diagnosis, e.g. "knee hurts, she said") is stored only when the
    family switched the consent flag on, because it is health information;
  * 2-140 characters, a fixed set of kinds, never a transcript.

The family sees the list only with the same consent flag as the conversation summaries (boundary 8); they may delete
any fact, with or without consent.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .db import get_db
from .deps import get_now, require_key

router = APIRouter(dependencies=[Depends(require_key)])

KINDS = ("person", "like", "dislike", "routine", "place", "event", "concern", "note")
MAX_FACTS = 200  # per person: the least used automatic fact makes room

_DIGITS = re.compile(r"[0-9०-९]")
_MONEY = re.compile(r"(?:₹|रुपय|रुपये|\brs\b|\brupee|पैसे|पगार|पेन्शन|\bsalary\b|\bpension\b|\bbank\b|बँक|खाते\b|\bupi\b)", re.I)
_ADDRESS = re.compile(
    r"(?:पत्ता|पत्त्य|\baddress\b|\broad\b|\bstreet\b|रोड|गल्ली|मजला|\bflat\b|फ्लॅट|इमारत|\bbuilding\b|कॉलनी|"
    r"\bcolony\b|\bpincode\b|पिनकोड|\bsociety\b|सोसायटी)",
    re.I,
)
_HEALTH = re.compile(
    r"(?:मधुमेह|डायबे|diabet|\bsugar\b|शुगर|\bbp\b|बीपी|ब्लड\s*प्रेशर|रक्तदाब|हृदयविकार|हार्ट|\bheart\b|कर्करोग|"
    r"कॅन्सर|\bcancer\b|अर्धांगवायू|\bstroke\b|\bdementia\b|विस्मरण|अस्थमा|\basthma\b|दमा\b|किडनी|\bkidney\b|"
    r"थायरॉईड|\bthyroid\b|डिप्रेशन|\bdepress|ट्यूमर|\btumou?r\b|\bhiv\b|एचआयव्ही|\bdiagnos|निदान|औषध|गोळी|गोळ्या|"
    r"\bmedicine|\btablet|\bdose\b|इंजेक्शन|\binjection\b|ऑपरेशन|\bsurgery\b|शस्त्रक्रिया)",
    re.I,
)
_SPLIT = re.compile(r"[\s,.?!।;:\"“”‘’()\[\]{}\-–—]+")


def reject_reason(fact: str, kind: str, consent: bool) -> str | None:
    """Why this fact must not be stored, or None when it may be. Pure; the tests call it directly."""
    text = fact.strip()
    if not 2 <= len(text) <= 140:
        return "length"
    if kind not in KINDS:
        return "kind"
    if _DIGITS.search(text):
        return "number"
    if _MONEY.search(text):
        return "money"
    if _ADDRESS.search(text):
        return "address"
    if _HEALTH.search(text):
        return "health"
    if kind == "concern" and not consent:
        return "concern_needs_consent"
    return None


def tokens(text: str) -> set[str]:
    return {t for t in _SPLIT.split(text.lower()) if len(t) >= 2}


def stem(token: str) -> str:
    """Marathi inflection ("आर्यनला", "आर्यनचं", "आर्यनने") keeps the first letters of the name."""
    return token[:4] if len(token) > 4 else token


def similarity(a: str, b: str) -> float:
    ta, tb = {stem(t) for t in tokens(a)}, {stem(t) for t in tokens(b)}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def subject(fact: str) -> str:
    """A person fact is written "आर्यन — नातू" (name, then relation): the name is what makes two such facts the same."""
    return fact.split("—", 1)[0].strip() if "—" in fact else ""


def same_fact(kind: str, text: str, other_kind: str, other: str) -> bool:
    if kind == "person" and other_kind == "person":
        a, b = subject(text), subject(other)
        if a and b and {stem(t) for t in tokens(a)} == {stem(t) for t in tokens(b)}:
            return True
    return similarity(text, other) >= 0.7


class FactIn(BaseModel):
    fact: str = Field(min_length=1, max_length=400)
    kind: Literal["person", "like", "dislike", "routine", "place", "event", "concern", "note"] = "note"
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    source: Literal["auto", "explicit"] = "auto"
    source_date: date | None = None


class FactOut(BaseModel):
    id: int
    fact: str
    kind: str
    source_date: date
    last_used: datetime | None
    confidence: float
    source: str


class FactSaved(FactOut):
    created: bool


class ForgetIn(BaseModel):
    match: str = Field(min_length=1, max_length=200)


def _out(f: m.UserFact) -> FactOut:
    return FactOut(
        id=f.id, fact=f.fact, kind=f.kind, source_date=f.source_date, last_used=f.last_used,
        confidence=f.confidence, source=f.source,
    )


def _user(db: Session, user_id: int) -> m.User:
    user = db.get(m.User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    return user


def _rows(db: Session, user_id: int) -> list[m.UserFact]:
    return list(db.scalars(select(m.UserFact).where(m.UserFact.user_id == user_id).order_by(m.UserFact.id)))


@router.post("/users/{user_id}/facts", response_model=FactSaved)
def save_fact(
    user_id: int, body: FactIn, db: Session = Depends(get_db), now: datetime = Depends(get_now)
) -> FactSaved:
    user = _user(db, user_id)
    text = re.sub(r"\s+", " ", body.fact).strip()
    why = reject_reason(text, body.kind, bool(user.consent_distress_alert))
    if why:
        raise HTTPException(422, f"not stored: {why}")
    day = body.source_date or now.date()
    rows = _rows(db, user_id)
    twin = next((r for r in rows if same_fact(body.kind, text, r.kind, r.fact)), None)
    if twin is not None:  # the same thing again: refresh it, never duplicate it
        if len(text) >= len(twin.fact) or body.kind == "person":
            twin.fact = text  # the newest wording of a person ("आर्यन — नातू") replaces the older one
        twin.source_date = max(twin.source_date, day)
        twin.confidence = max(twin.confidence, body.confidence)
        if body.source == "explicit":
            twin.source = "explicit"
        db.commit()
        return FactSaved(**_out(twin).model_dump(), created=False)
    if len(rows) >= MAX_FACTS:  # make room: the least recently used, lowest-confidence automatic fact goes first
        victim = min(
            (r for r in rows if r.source == "auto"),
            key=lambda r: (r.last_used or datetime.min, r.confidence, r.id),
            default=None,
        )
        if victim is None:
            raise HTTPException(409, "too many facts")
        db.delete(victim)
    fact = m.UserFact(
        user_id=user_id, fact=text, kind=body.kind, source_date=day, confidence=body.confidence, source=body.source,
    )
    db.add(fact)
    db.commit()
    return FactSaved(**_out(fact).model_dump(), created=True)


@router.get("/users/{user_id}/facts", response_model=list[FactOut])
def list_facts(
    user_id: int, audience: Literal["arjun", "family"] = "arjun", limit: int = 100, db: Session = Depends(get_db)
) -> list[FactOut]:
    """`audience=family` is the dashboard: empty unless the family switched the consent flag on (boundary 8)."""
    user = _user(db, user_id)
    if audience == "family" and not user.consent_distress_alert:
        return []
    rows = sorted(_rows(db, user_id), key=lambda r: (r.source_date, r.id), reverse=True)
    return [_out(r) for r in rows[: max(1, min(limit, 200))]]


@router.delete("/users/{user_id}/facts/{fact_id}", status_code=204)
def delete_fact(user_id: int, fact_id: int, db: Session = Depends(get_db)) -> None:
    fact = db.get(m.UserFact, fact_id)
    if fact is None or fact.user_id != user_id:
        raise HTTPException(404, "fact not found")
    db.delete(fact)
    db.commit()


@router.post("/users/{user_id}/facts/forget", response_model=list[FactOut])
def forget_matching(user_id: int, body: ForgetIn, db: Session = Depends(get_db)) -> list[FactOut]:
    """"हे विसरून जा": delete the ONE fact that best matches her words (at least one shared word). Returns what went."""
    _user(db, user_id)
    want = {stem(t) for t in tokens(body.match)}
    best: tuple[float, m.UserFact] | None = None
    for r in _rows(db, user_id):
        have = {stem(t) for t in tokens(r.fact)}
        shared = len(want & have)
        if shared == 0:
            continue
        score = shared / max(1, len(want | have))
        if best is None or score > best[0] or (score == best[0] and r.id > best[1].id):
            best = (score, r)
    if best is None:
        return []
    gone = _out(best[1])
    db.delete(best[1])
    db.commit()
    return [gone]


@router.post("/users/{user_id}/facts/{fact_id}/used", status_code=204)
def touch_fact(user_id: int, fact_id: int, db: Session = Depends(get_db), now: datetime = Depends(get_now)) -> None:
    fact = db.get(m.UserFact, fact_id)
    if fact is not None and fact.user_id == user_id:
        fact.last_used = now
        db.commit()
