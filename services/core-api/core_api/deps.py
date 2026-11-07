"""Shared FastAPI dependencies (kept apart from main.py so routers can import them)."""

import hmac
import os
from datetime import datetime

from fastapi import Depends, Header, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .clock import local_now
from .db import get_db


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


def require_key(
    request: Request,
    response: Response,
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> None:
    expected = os.environ.get("CORE_API_KEY")
    key_ok = bool(expected) and hmac.compare_digest((x_api_key or "").encode(), (expected or "").encode())
    if key_ok:
        return
    if not auth_enabled():
        if not expected and testing():
            return
        if not expected:
            raise HTTPException(503, "CORE_API_KEY not configured")
        raise HTTPException(401, "invalid api key")
    if testing() and os.environ.get("ARJUN_AUTH") != "1":
        return
    from .auth import authorize_core_request

    authorize_core_request(request, response, db)


def auth_enabled() -> bool:
    return os.environ.get("ARJUN_AUTH", "0").strip() == "1"
