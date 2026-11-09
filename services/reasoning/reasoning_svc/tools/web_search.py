"""Live web search through the Tavily Search API (the only search provider).

Contract: `search(query, lang)` returns up to three {title, snippet, source_domain} dicts, or None on ANY failure (no key,
timeout, HTTP error, bad JSON, rate limit). It never raises. `search(..., full=True)` is the "answer any question" mode
(2026-11-09): Tavily `advanced` depth, 5 results, Tavily's own short answer (`include_answer: "basic"`), `topic: news` +
`time_range` for current events, low-score (< 0.5) results dropped and stale ones (older than `max_age_days`, by the
published date, measured in CODE against today's date) dropped. It returns {"answer": str, "results": [...]}, each result
also carrying `score` and `age_days` (None when the page has no date).
The API key is read from the environment at call time and is never logged or returned. Calls are spaced by a small
process-wide limiter (1 request/second) and identical queries are served from a 10-minute cache. Results are third-party
text: callers pass them to the LLM as data and never speak URLs.
"""

from __future__ import annotations

import html
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import httpx

log = logging.getLogger("arjun.websearch")

URL = "https://api.tavily.com/search"
TIMEOUT_S = 4.0  # total budget for one search, retry included
CACHE_TTL_S = 600.0
MIN_INTERVAL_S = 1.0  # polite spacing: one request per second
MAX_RESULTS = 3  # the legacy (non-full) mode
FULL_MAX_RESULTS = 5
MIN_SCORE = 0.5  # Tavily relevance below this is dropped
_TAG = re.compile(r"<[^>]+>")

_lock = threading.Lock()
_cache: dict[tuple[Any, ...], tuple[float, Any]] = {}
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


def age_days(published: Any, today: date) -> int | None:
    """Whole days between a result's published date and `today`; None when it has no usable date."""
    raw = str(published or "").strip()
    if not raw:
        return None
    parsed: datetime | None = None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return max(0, (today - parsed.date()).days)


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
    full: bool = False,
    news: bool = False,
    time_range: str | None = None,
    max_age_days: int | None = None,
    today: date | None = None,
) -> Any:
    key = (os.environ.get("TAVILY_API_KEY") or "").strip()
    query = " ".join((query or "").split())[:300 if full else 200]
    if not key or not query:
        return None
    domains = [d.lower() for d in (domains or [])][:5]
    today = today or date.today()
    cache_key = (query.casefold(), lang, tuple(domains), full, news, time_range, max_age_days)
    now = clock()
    with _lock:
        hit = _cache.get(cache_key)
        if hit and now - hit[0] < CACHE_TTL_S:
            return _copy(hit[1])
    deadline = now + timeout_s
    body: dict[str, Any] = {
        "query": query,
        "max_results": FULL_MAX_RESULTS if full else MAX_RESULTS,
        "search_depth": "advanced" if full else "basic",
        "include_answer": "basic" if full else False,
        "topic": "news" if (domains or news) else "general",  # approved domains = news, always
    }
    if body["topic"] == "news" and (time_range or full):
        body["time_range"] = time_range or "week"
    elif time_range:
        body["time_range"] = time_range
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
                payload = r.json()
                items = payload.get("results") or []
            except (ValueError, AttributeError):
                return None
            results: list[dict[str, Any]] = []
            for it in items:
                title, snippet = _clean(it.get("title")), _clean(it.get("content"))
                host = host_of(str(it.get("url") or ""))
                if domains and not host_allowed(host, domains):
                    continue  # post-filter: a non-approved source is dropped even if the API returned it
                if not (title or snippet):
                    continue
                row: dict[str, Any] = {"title": title, "snippet": snippet, "source_domain": host}
                if full:
                    score = it.get("score")
                    row["score"] = float(score) if isinstance(score, (int, float)) else None
                    row["age_days"] = age_days(it.get("published_date"), today)
                    if row["score"] is not None and row["score"] < MIN_SCORE:
                        continue  # low relevance
                    if max_age_days is not None and row["age_days"] is not None and row["age_days"] > max_age_days:
                        continue  # stale: judged by the page's date against today, never by what its text claims
                results.append(row)
                if len(results) == (FULL_MAX_RESULTS if full else MAX_RESULTS):
                    break
            answer = _clean(payload.get("answer")) if full else ""
            if not results:
                return None
            out: Any = {"answer": answer, "results": results} if full else results
            with _lock:
                _cache[cache_key] = (clock(), out)
            return _copy(out)
        return None
    except Exception as exc:  # noqa: BLE001 - search must never break a turn
        log.info("web search error: %s", type(exc).__name__)
        return None
    finally:
        if client is None:
            http.close()


def _copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {"answer": value["answer"], "results": [dict(x) for x in value["results"]]}
    return [dict(x) for x in value]
