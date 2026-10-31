"""Weekly appointment occurrences.

A row with `weekdays` is a repeating rule: `starts_at` is the first day the rule applies, and `start_time` is when
each occurrence starts. A row without `weekdays` is a one-off appointment (unchanged). Nothing here invents a date:
an occurrence exists only on a configured weekday, on or after the rule's first day.
"""

from datetime import datetime, timedelta

from . import models as m


def _at(day, hhmm: str) -> datetime:  # type: ignore[no-untyped-def]
    h, mi = (int(x) for x in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, mi)


def occurrence_on(appt: m.Appointment, day) -> datetime | None:  # type: ignore[no-untyped-def]
    """This appointment's occurrence on `day`, or None."""
    if not appt.weekdays:
        return appt.starts_at if appt.starts_at.date() == day else None
    if day < appt.starts_at.date() or day.weekday() not in appt.weekdays:
        return None
    return _at(day, appt.start_time or appt.starts_at.strftime("%H:%M"))


def next_occurrence(appt: m.Appointment, now: datetime) -> datetime | None:
    """The first occurrence at or after `now`, or None."""
    if not appt.weekdays:
        return appt.starts_at if appt.starts_at >= now else None
    start = max(now.date(), appt.starts_at.date())
    for offset in range(0, 8):  # every configured weekday occurs within one week
        when = occurrence_on(appt, start + timedelta(days=offset))
        if when is not None and when >= now:
            return when
    return None


def occurrence_end(appt: m.Appointment, start: datetime) -> datetime | None:
    """When the occurrence ends, for display only (`end_time` is optional)."""
    if not appt.end_time:
        return None
    end = _at(start.date(), appt.end_time)
    return end + timedelta(days=1) if end <= start else end
