"""Short-lived signed links that let the family join the elder's LiveKit room.

A link is `<user_id>.<expires_unix>.<signature>`: HMAC-SHA256 over the first two fields with JOIN_SECRET
(or CORE_API_KEY when that is unset). No database row is needed, so any core-api replica can check it.
Links live for 30 minutes; an expired link is rejected.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from urllib.parse import quote

TTL_S = 30 * 60


def _secret() -> bytes:
    return (os.environ.get("JOIN_SECRET") or os.environ.get("CORE_API_KEY") or "").encode()


def _sign(payload: str) -> str:
    digest = hmac.new(_secret(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def issue(user_id: int, now: float | None = None) -> str:
    expires = int(now if now is not None else time.time()) + TTL_S
    payload = f"{user_id}.{expires}"
    return f"{payload}.{_sign(payload)}"


def verify(token: str, now: float | None = None) -> int | None:
    """The user id this link belongs to, or None when it is malformed, forged or expired."""
    parts = (token or "").split(".")
    if len(parts) != 3:
        return None
    uid_s, exp_s, sig = parts
    if not uid_s.isdigit() or not exp_s.isdigit():
        return None
    payload = f"{uid_s}.{exp_s}"
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    if int(exp_s) <= int(now if now is not None else time.time()):
        return None
    return int(uid_s)


def join_url(user_id: int, now: float | None = None) -> str:
    """The web page the Telegram button opens, or "" when BASE_URL is not configured."""
    base = os.environ.get("BASE_URL", "").strip().rstrip("/")
    if not base:
        return ""
    return f"{base}/?view=join&t={quote(issue(user_id, now))}"
