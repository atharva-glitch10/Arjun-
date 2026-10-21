"""Household wall-clock time. Containers run in UTC, so bare datetime.now() would be 5h30 off."""

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
    """Naive wall-clock time in the household timezone (default Asia/Kolkata)."""
    zone = _zone()
    return datetime.now(zone).replace(tzinfo=None) if zone else datetime.now()
