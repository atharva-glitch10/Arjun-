"""Shared FastAPI dependencies (kept apart from main.py so routers can import them)."""

import hmac
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


def testing() -> bool:
    """Only the test suites set ARJUN_TESTING=1; it is the one way to run without CORE_API_KEY."""
    return os.environ.get("ARJUN_TESTING") == "1"


def check_api_key_configured() -> None:
    """Fail closed: an empty CORE_API_KEY used to silently disable auth. Called at startup."""
    if not os.environ.get("CORE_API_KEY") and not testing():
        raise SystemExit(
            "core-api: CORE_API_KEY is empty. Set it in the root .env (any long random string). "
            "Only the test suites may run without it (ARJUN_TESTING=1)."
        )


def require_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = os.environ.get("CORE_API_KEY")
    if not expected:
        if testing():
            return
        raise HTTPException(503, "CORE_API_KEY not configured")
    # constant-time comparison so the key can't be guessed byte by byte from response timing
    if not hmac.compare_digest((x_api_key or "").encode(), expected.encode()):
        raise HTTPException(401, "invalid api key")
