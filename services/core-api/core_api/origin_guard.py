"""CSRF brake: refuse a cookie-carrying browser request that comes from another site (deadline hardening, 2026-11-10).

Session and device cookies are SameSite=Lax, which already stops most cross-site POSTs; this adds an explicit check. An unsafe
request (POST / PUT / PATCH / DELETE) whose `Origin` header is PRESENT must come from BASE_URL or from localhost, else 403.
It only applies when there is something to forge: account auth is on (ARJUN_AUTH=1) or the request carries an arjun_session /
arjun_device cookie. The API-key services (voice-agent, reasoning, scheduler) and the Vite proxy's key-injected calls send no
cookie, so they are never affected. A request with no Origin (curl, httpx, server-to-server) is allowed."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse

from .deps import auth_enabled

UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_LOCAL = frozenset({"localhost", "127.0.0.1", "::1"})


def _origin_of(url: str) -> tuple[str, str, int | None] | None:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return None
    return p.scheme, p.hostname.lower(), p.port


def origin_allowed(origin: str, base_url: str | None = None) -> bool:
    """True for localhost (any port) and for the BASE_URL origin. The literal "null" (a sandboxed page) is refused."""
    got = _origin_of(origin)
    if got is None:
        return False
    scheme, host, port = got
    if host in _LOCAL:
        return True
    base = _origin_of(base_url if base_url is not None else os.environ.get("BASE_URL", "").strip())
    if base is None:
        return False
    b_scheme, b_host, b_port = base
    default = {"http": 80, "https": 443}
    return scheme == b_scheme and host == b_host and (port or default[scheme]) == (b_port or default[b_scheme])


def _has_credentials(request: Request) -> bool:
    return auth_enabled() or "arjun_session" in request.cookies or "arjun_device" in request.cookies


async def origin_brake(request: Request, call_next):  # type: ignore[no-untyped-def]
    if request.method in UNSAFE:
        origin = request.headers.get("origin")
        if origin is not None and _has_credentials(request) and not origin_allowed(origin):
            return JSONResponse({"detail": "cross-site request refused"}, status_code=403, headers={"Cache-Control": "no-store"})
    return await call_next(request)
