"""Shared FastAPI dependencies (kept apart from main.py so routers can import them)."""

import os
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Header, HTTPException

_IST = timezone(timedelta(hours=5, minutes=30), "IST")


def _zone() -> tzinfo | None:
    name = os.environ.get("ARJUN_TZ", "Asia/Kolkata")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return _IST if name == "Asia/Kolkata" else None  # tzdata missing: IST has no DST


def local_now() -> datetime:
    """Wall-clock time in the household's timezone (default Asia/Kolkata), naive.

    Containers run in UTC, so a bare `datetime.now()` would put every reminder 5h30 off.
    """
    zone = _zone()
    return datetime.now(zone).replace(tzinfo=None) if zone else datetime.now()


def get_now() -> datetime:
    """Naive user-local 'now'. Overridden in tests."""
    return local_now()


def require_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = os.environ.get("CORE_API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(401, "invalid api key")
