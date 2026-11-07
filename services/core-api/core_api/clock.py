"""Household-local clock helpers kept separate from FastAPI dependencies."""

import os
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_IST = timezone(timedelta(hours=5, minutes=30), "IST")


def _zone() -> tzinfo | None:
    name = os.environ.get("ARJUN_TZ", "Asia/Kolkata")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return _IST if name == "Asia/Kolkata" else None


def local_now() -> datetime:
    """Naive household-local wall clock (IST fallback has no DST)."""
    zone = _zone()
    return datetime.now(zone).replace(tzinfo=None) if zone else datetime.now()
