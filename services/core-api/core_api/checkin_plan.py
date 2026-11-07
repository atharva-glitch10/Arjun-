"""Today's check-in plan, built only from the elder's own data (SQL): never a hard-coded name or time.

  kind        due                          asks
  sleep       wake_time + 30 min           how she slept
  breakfast   breakfast_time + 30 min      breakfast
  lunch       lunch_time + 30 min          lunch (and what she had)
  snack       snack_time + 30 min          the evening snack
  dinner      dinner_time + 30 min         dinner
  walk        walk_time (if set)           a short walk
  bp          bp_check_time (if set)       the BP check (numbers are read in the readings flow)
  sugar       sugar_check_time (if set)    the fasting sugar check
  sugar_after sugar_after_time (if set)    the after-lunch sugar check
  interest    1/4 into the opener window   "do you want to listen to <interest>?" (a listening interest only)
  home        4/5 into the opener window   whether she spoke to one family member today
  appt<ID>    1 h before an appointment    "do you remember it?"
  rem<ID>     1 h before a reminder        "do you remember it?"

Medicines are NOT planned here. The medicine flow (medicines.py) already asks at the due time and again every
repeat_minutes, with the name and dose exactly as the family entered them; the day card reads those doses directly.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .recurrence import occurrence_on

# Interests that can be listened to. A cooking interest is not offered (Arjun never recites recipes, boundary 10).
LISTENING = ("गाणी", "गाणे", "गाणं", "भजन", "अभंग", "कीर्तन", "आरती", "संगीत", "भक्तिगीत", "गीत", "बातम्या", "songs", "music", "bhajan")
# Contacts that count as "home". A doctor never does.
FAMILY = ("मुलगा", "मुलगी", "नात", "नातू", "सून", "जावई", "भाऊ", "बहीण", "नवरा", "पती", "पत्नी", "आई", "वडील", "family", "son", "daughter", "grandson", "granddaughter", "brother", "sister")
LEAD = timedelta(hours=1)  # an appointment / reminder is mentioned this long before it
MIN_LEAD_AT_CREATION = timedelta(minutes=30)  # a plan row for a thing that is about to start is not created


@dataclass(frozen=True)
class PlanItem:
    kind: str
    due_at: datetime
    ref: str = ""


def hm(value: str) -> time:
    h, mi = (int(x) for x in value.split(":"))
    return time(h, mi)


def at(day: date, value: str | time) -> datetime:
    t = hm(value) if isinstance(value, str) else value
    return datetime.combine(day, t)


def first_name(full: str) -> str:
    """"राहुल" from "राहुल पाटील"; keeps a single word as it is."""
    parts = full.strip().split()
    return parts[0] if parts else ""


def listening_interest(user: m.User, day: date) -> str:
    """One listening interest for the day (rotating through them), or "" when she has none."""
    pool = [i for i in (user.interests or []) if any(w in i.lower() for w in LISTENING)]
    return pool[day.toordinal() % len(pool)] if pool else ""


def family_contact(contacts: list[m.Contact], day: date) -> m.Contact | None:
    pool = [c for c in contacts if any(w in c.relation.lower() for w in FAMILY)]
    return pool[day.toordinal() % len(pool)] if pool else None


def _window_point(user: m.User, day: date, fraction: float) -> datetime:
    start, end = at(day, user.opener_start), at(day, user.opener_end)
    if end <= start:
        return start
    return (start + (end - start) * fraction).replace(second=0, microsecond=0)


def build_plan(db: Session, user: m.User, now: datetime) -> list[PlanItem]:
    day = now.date()
    wake = at(day, user.wake_time)
    items = [
        PlanItem("sleep", wake + timedelta(minutes=30)),
        PlanItem("breakfast", at(day, user.breakfast_time) + timedelta(minutes=30)),
        PlanItem("lunch", at(day, user.lunch_time) + timedelta(minutes=30)),
        PlanItem("snack", at(day, user.snack_time) + timedelta(minutes=30)),
        PlanItem("dinner", at(day, user.dinner_time) + timedelta(minutes=30)),
    ]
    if user.walk_time:
        items.append(PlanItem("walk", at(day, user.walk_time)))
    if user.bp_check_time:
        items.append(PlanItem("bp", at(day, user.bp_check_time)))
    if user.sugar_check_time:
        items.append(PlanItem("sugar", at(day, user.sugar_check_time), "fasting"))
    if user.sugar_after_time:
        items.append(PlanItem("sugar_after", at(day, user.sugar_after_time), "after_meal"))
    interest = listening_interest(user, day)
    if interest:
        items.append(PlanItem("interest", _window_point(user, day, 0.25), interest))
    contacts = list(db.scalars(select(m.Contact).where(m.Contact.user_id == user.id).order_by(m.Contact.id)))
    person = family_contact(contacts, day)
    if person is not None:
        items.append(PlanItem("home", _window_point(user, day, 0.8), f"{first_name(person.name)}|{person.relation}"))

    start, end = datetime.combine(day, time.min), datetime.combine(day, time.min) + timedelta(days=1)
    for a in db.scalars(select(m.Appointment).where(m.Appointment.user_id == user.id)):
        when = occurrence_on(a, day)
        if when is not None and when - now >= MIN_LEAD_AT_CREATION:
            items.append(PlanItem(f"appt{a.id}", when - LEAD, f"{when:%H:%M}|{a.title}"))
    for r in db.scalars(
        select(m.Reminder).where(
            m.Reminder.user_id == user.id, m.Reminder.status != "done", m.Reminder.due_at >= start, m.Reminder.due_at < end
        )
    ):
        if r.due_at - now >= MIN_LEAD_AT_CREATION:
            items.append(PlanItem(f"rem{r.id}", r.due_at - LEAD, f"{r.due_at:%H:%M}|{r.task}"))
    return sorted(items, key=lambda i: (i.due_at, i.kind))
