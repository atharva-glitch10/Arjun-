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


def issue(user_id: int, now: float | None = None, call_id: int | None = None) -> str:
    expires = int(now if now is not None else time.time()) + TTL_S
    payload = f"{user_id}.{expires}" + (f".{call_id}" if call_id is not None else "")
    return f"{payload}.{_sign(payload)}"


def claims(token: str, now: float | None = None) -> tuple[int, int | None] | None:
    """Signed user/call identity, or None when malformed, forged or expired."""
    parts = (token or "").split(".")
    if len(parts) not in (3, 4):
        return None
    uid_s, exp_s = parts[:2]
    call_s = parts[2] if len(parts) == 4 else None
    sig = parts[-1]
    if not uid_s.isdigit() or not exp_s.isdigit() or call_s is not None and not call_s.isdigit():
        return None
    payload = ".".join(parts[:-1])
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    if int(exp_s) <= int(now if now is not None else time.time()):
        return None
    return int(uid_s), int(call_s) if call_s is not None else None


def verify(token: str, now: float | None = None) -> int | None:
    result = claims(token, now)
    return None if result is None else result[0]


def join_url(user_id: int, now: float | None = None, call_id: int | None = None) -> str:
    """The web page the Telegram button opens, or "" when BASE_URL is not configured."""
    base = os.environ.get("BASE_URL", "").strip().rstrip("/")
    if not base:
        return ""
    return f"{base}/?view=join&t={quote(issue(user_id, now, call_id))}"
