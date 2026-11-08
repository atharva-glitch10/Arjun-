"""Live web search through the Tavily Search API (the only search provider).

Contract: `search(query, lang)` returns up to three {title, snippet, source_domain} dicts, or None on ANY failure (no key, timeout,
HTTP error, bad JSON, rate limit). It never raises. The API key is read from the environment at call time and is
never logged or returned. Calls are spaced by a small process-wide limiter (1 request/second) and
identical queries are served from a 10-minute cache. Results are third-party text: callers pass them to the LLM as
data and never speak URLs.
"""

from __future__ import annotations

import html
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpx

log = logging.getLogger("arjun.websearch")

URL = "https://api.tavily.com/search"
TIMEOUT_S = 4.0  # total budget for one search, retry included
CACHE_TTL_S = 600.0
MIN_INTERVAL_S = 1.0  # polite spacing: one request per second
MAX_RESULTS = 3
_TAG = re.compile(r"<[^>]+>")

_lock = threading.Lock()
_cache: dict[tuple[str, str], tuple[float, list[dict[str, str]]]] = {}
_last_call = [-1e9]  # monotonic time of the last request that went out


def reset() -> None:
    """Forget the cache and the limiter (tests)."""
    with _lock:
        _cache.clear()
        _last_call[0] = -1e9


def available() -> bool:
    return bool((os.environ.get("TAVILY_API_KEY") or "").strip())


def host_of(url: str) -> str:
    host = (urlparse(url if "//" in url else "//" + url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def host_allowed(url: str, domains: list[str]) -> bool:
    host = host_of(url)
    return bool(host) and any(host == d or host.endswith("." + d) for d in domains)


def _clean(text: Any) -> str:
    return " ".join(html.unescape(_TAG.sub("", str(text or ""))).split())


def _reserve_slot(deadline: float, clock: Callable[[], float]) -> float | None:
    """Seconds to wait before a request may go out, or None if that would pass the deadline. Reserves the slot."""
    with _lock:
        now = clock()
        start = max(now, _last_call[0] + MIN_INTERVAL_S)
        if start > deadline:
            return None
        _last_call[0] = start
        return start - now


def search(
    query: str,
    lang: str = "mr",
    *,
    client: httpx.Client | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    timeout_s: float = TIMEOUT_S,
    domains: list[str] | None = None,
) -> list[dict[str, str]] | None:
    key = (os.environ.get("TAVILY_API_KEY") or "").strip()
    query = " ".join((query or "").split())[:200]
    if not key or not query:
        return None
    domains = [d.lower() for d in (domains or [])][:5]
    cache_key = (query.casefold(), lang, tuple(domains))
    now = clock()
    with _lock:
        hit = _cache.get(cache_key)
        if hit and now - hit[0] < CACHE_TTL_S:
            return [dict(x) for x in hit[1]]
    deadline = now + timeout_s
    body: dict[str, Any] = {
        "query": query, "max_results": MAX_RESULTS, "search_depth": "basic", "include_answer": False,
        "topic": "news" if domains else "general",  # news = only the family's approved domains
    }
    if domains:
        body["include_domains"] = domains
    headers = {"Authorization": f"Bearer {key}"}
    http = client or httpx.Client()
    try:
        for attempt in (1, 2):  # one retry, only for a timeout, a 429 or a 5xx
            wait = _reserve_slot(deadline, clock)
            if wait is None:
                log.info("web search skipped: rate limit")
                return None
            if wait > 0:
                sleep(wait)
            remaining = deadline - clock()
            if remaining <= 0.2:
                return None
            try:
                r = http.post(URL, json=body, headers=headers, timeout=remaining)
            except httpx.TimeoutException:
                log.info("web search timeout (attempt %d)", attempt)
                continue
            except httpx.HTTPError as exc:
                log.info("web search failed: %s", type(exc).__name__)
                return None
            if r.status_code == 429 or r.status_code >= 500:
                log.info("web search http %d (attempt %d)", r.status_code, attempt)
                continue
            if r.status_code != 200:
                log.info("web search http %d", r.status_code)
                return None
            try:
                items = r.json().get("results") or []
            except ValueError:
                return None
            results = []
            for it in items:
                title, snippet = _clean(it.get("title")), _clean(it.get("content"))
                host = host_of(str(it.get("url") or ""))
                if domains and not host_allowed(host, domains):
                    continue  # post-filter: a non-approved source is dropped even if the API returned it
                if title or snippet:
                    results.append({"title": title, "snippet": snippet, "source_domain": host})
                if len(results) == MAX_RESULTS:
                    break
            if not results:
                return None
            with _lock:
                _cache[cache_key] = (clock(), results)
            return [dict(x) for x in results]
        return None
    except Exception as exc:  # noqa: BLE001 - search must never break a turn
        log.info("web search error: %s", type(exc).__name__)
        return None
    finally:
        if client is None:
            http.close()
