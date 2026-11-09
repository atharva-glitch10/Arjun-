"""Is BASE_URL a link a family member can actually open? (2026-11-09: a Telegram "join call" button pointed at a dead
Cloudflare quick-tunnel URL, DNS_PROBE_FINISHED_NXDOMAIN.)

`check()` answers {url, https, reachable, kind, ok, reason}. The rules: BASE_URL must be https, a `*.trycloudflare.com`
quick tunnel is refused unless ARJUN_ALLOW_QUICK_TUNNEL=1 (those URLs die whenever the tunnel process restarts), and the
URL must answer an HTTP GET within 3 s (any status below 500). The answer is cached for 60 s so a burst of alerts probes
once. No secret is ever read or returned: only the URL, which is not a secret. The reason text is for logs and the dashboard."""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpx

log = logging.getLogger("arjun.baseurl")

CACHE_S = 60.0
TIMEOUT_S = 3.0
TAILSCALE_URL = "https://odin.tail7a9105.ts.net"
FIX_HINT = f"Fix: set BASE_URL to the Tailscale Funnel URL ({TAILSCALE_URL}) or another stable https URL."
LINK_DOWN_TEXT = "⚠️ लिंक उपलब्ध नाही, कृपया थेट फोन करा. (Link unavailable, please call directly.)"

_lock = threading.Lock()
_cache: dict[tuple[str, bool], tuple[float, dict[str, Any]]] = {}


def _default_fetch(url: str, timeout: float) -> int:
    """HTTP status of GET `url`. Raises on DNS / connection / timeout errors."""
    return httpx.get(url, timeout=timeout, follow_redirects=True).status_code


_fetch: Callable[[str, float], int] = _default_fetch  # replaced in tests: the network is never touched there


def reset() -> None:
    with _lock:
        _cache.clear()


def kind_of(url: str) -> str:
    """none | invalid | http | quick-tunnel | tailscale | https."""
    if not url:
        return "none"
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host:
        return "invalid"
    if parsed.scheme != "https":
        return "http"
    if host == "trycloudflare.com" or host.endswith(".trycloudflare.com"):
        return "quick-tunnel"
    if host.endswith(".ts.net"):
        return "tailscale"
    return "https"


def _evaluate(url: str, allow_quick: bool) -> dict[str, Any]:
    kind = kind_of(url)
    out: dict[str, Any] = {"url": url, "https": url.lower().startswith("https://"), "reachable": False, "kind": kind,
                           "ok": False, "reason": ""}
    if kind == "none":
        out["reason"] = "BASE_URL is not set"
    elif kind == "invalid":
        out["reason"] = "BASE_URL is not a valid URL"
    elif kind == "http":
        out["reason"] = "BASE_URL is not https (browsers and Telegram need an https link)"
    elif kind == "quick-tunnel" and not allow_quick:
        out["reason"] = "BASE_URL is a trycloudflare.com quick tunnel (it dies when the tunnel restarts); set ARJUN_ALLOW_QUICK_TUNNEL=1 to allow it"
    else:
        try:
            status = _fetch(url + "/", TIMEOUT_S)
            out["reachable"] = status < 500
            out["reason"] = "" if out["reachable"] else f"BASE_URL answered HTTP {status}"
        except Exception as exc:  # noqa: BLE001 - DNS failure, refused, timeout: all mean "do not send this link"
            out["reason"] = f"BASE_URL is unreachable ({type(exc).__name__})"
        out["ok"] = bool(out["reachable"])
    return out


def check(url: str | None = None, *, clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """The cached verdict on `url` (default: BASE_URL from the environment)."""
    url = (os.environ.get("BASE_URL", "") if url is None else url).strip().rstrip("/")
    allow_quick = os.environ.get("ARJUN_ALLOW_QUICK_TUNNEL", "").strip() == "1"
    key = (url, allow_quick)
    now = clock()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_S:
            return dict(hit[1])
    result = _evaluate(url, allow_quick)
    with _lock:
        _cache[key] = (clock(), result)
    return dict(result)


def configured() -> bool:
    return bool(os.environ.get("BASE_URL", "").strip())


def guard_link(join_url: str | None) -> tuple[str | None, str]:
    """(link to send, extra line for the message). A dead / refused BASE_URL gives (None, LINK_DOWN_TEXT) and a clear log line;
    the alert itself is still sent, only without the dead button. No BASE_URL at all keeps the old behaviour (no link)."""
    if not join_url:
        return join_url, ""
    verdict = check()
    if verdict["ok"]:
        return join_url, ""
    log.warning("family call link NOT sent (%s): %s | %s", verdict["kind"], verdict["reason"], FIX_HINT)
    return None, LINK_DOWN_TEXT


def status_line(verdict: dict[str, Any] | None = None) -> str:
    """One line for the startup log and dev-up: `BASE_URL ok|unreachable|quick-tunnel|not-set|not-https ...` (no secrets)."""
    v = verdict or check()
    if v["ok"]:
        return f"BASE_URL ok: {v['url']} ({v['kind']})"
    state = {"none": "not-set", "http": "not-https", "invalid": "invalid", "quick-tunnel": "quick-tunnel"}.get(v["kind"], "unreachable")
    if v["kind"] == "quick-tunnel" and v["reachable"] is False and os.environ.get("ARJUN_ALLOW_QUICK_TUNNEL", "").strip() == "1":
        state = "unreachable"
    return f"BASE_URL {state}: {v['url'] or '(empty)'} - {v['reason']}. {FIX_HINT}"
