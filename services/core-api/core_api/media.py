"""Media for the elder screen: YouTube search (key stays here) and news headlines from the family's RSS feeds.

YouTube search.list costs 100 of the 10,000 daily quota units, so every query is cached 24 h in SQLite, the number
of uncached calls per day is capped, and a quota error from Google stops further calls until tomorrow. With no
`YOUTUBE_API_KEY` the endpoint answers 503 `youtube_not_configured` and reasoning opens the YouTube results page
instead. Headlines are copied VERBATIM from the feeds (HTML stripped, 120 characters at most): nothing is
summarised or written by a model.
"""

import html
import os
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .db import get_db
from .deps import get_now, require_key

router = APIRouter(dependencies=[Depends(require_key)])

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
CACHE_TTL = timedelta(hours=24)
NEWS_TTL_S = 15 * 60.0
NEWS_TOP = 5
TITLE_MAX = 120
FEED_TIMEOUT_S = 5.0

_daily: dict[str, Any] = {"day": None, "calls": 0, "blocked": False}
_news_cache: dict[tuple[Any, ...], tuple[float, list[dict[str, str]]]] = {}
_clock = time.monotonic  # replaced in tests


def http_get(url: str, params: dict[str, Any] | None = None, timeout: float = 5.0) -> httpx.Response:
    """The only network call in this module (tests replace it; no real network in tests)."""
    return httpx.get(url, params=params, timeout=timeout, follow_redirects=True,
                     headers={"User-Agent": "ArjunCompanion/1.0 (family news reader)"})


def normalise_query(q: str) -> str:
    return " ".join(unicodedata.normalize("NFC", q).casefold().split())[:200]


def _max_searches_per_day() -> int:
    try:
        return max(1, int(os.environ.get("YOUTUBE_MAX_SEARCHES_PER_DAY", "80")))  # 80 x 100 = 8,000 of 10,000 units
    except ValueError:
        return 80


def reset_quota_for_tests() -> None:
    _daily.update(day=None, calls=0, blocked=False)
    _news_cache.clear()


def _spend_quota(today: date) -> None:
    if _daily["day"] != today:
        _daily.update(day=today, calls=0, blocked=False)
    if _daily["blocked"] or _daily["calls"] >= _max_searches_per_day():
        raise HTTPException(429, "youtube_quota")
    _daily["calls"] += 1


@router.get("/media/youtube/search")
def youtube_search(
    q: str, user_id: int, db: Session = Depends(get_db), now: datetime = Depends(get_now)
) -> list[dict[str, str]]:
    if db.get(m.User, user_id) is None:
        raise HTTPException(404, "user not found")
    key = normalise_query(q)
    if not key:
        raise HTTPException(422, "empty search")
    row = db.get(m.YoutubeSearchCache, key)
    if row is not None and now - row.created_at < CACHE_TTL:
        return row.results
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(503, "youtube_not_configured")
    _spend_quota(now.date())
    params = {
        "part": "snippet", "q": q.strip()[:100], "type": "video", "videoEmbeddable": "true", "safeSearch": "strict",
        "relevanceLanguage": "mr", "regionCode": "IN", "maxResults": 5, "key": api_key,
    }
    try:
        r = http_get(YOUTUBE_SEARCH_URL, params, 5.0)
    except httpx.HTTPError as exc:
        raise HTTPException(502, "youtube_unreachable") from exc
    if r.status_code in (403, 429):
        if "quota" in r.text.lower():
            _daily["blocked"] = True  # no more calls today
            raise HTTPException(429, "youtube_quota")
        raise HTTPException(502, "youtube_refused")
    if r.status_code >= 400:
        raise HTTPException(502, "youtube_error")
    results = []
    for item in r.json().get("items", []):
        vid = (item.get("id") or {}).get("videoId")
        snippet = item.get("snippet") or {}
        if vid:
            results.append({
                "video_id": vid,
                "title": html.unescape(snippet.get("title", ""))[:TITLE_MAX],
                "channel": html.unescape(snippet.get("channelTitle", ""))[:80],
            })
    if row is None:
        db.add(m.YoutubeSearchCache(query_key=key, results=results, created_at=now))
    else:
        row.results, row.created_at = results, now
    db.commit()
    return results


# ---- news ---------------------------------------------------------------------------------------------------
_TAG = re.compile(r"<[^>]*>")


def clean_title(raw: str | None) -> str:
    """Plain text: tags removed, entities decoded, whitespace collapsed, at most 120 characters. Nothing else changes."""
    text = html.unescape(_TAG.sub(" ", html.unescape(raw or "")))
    text = " ".join(text.split())
    if len(text) <= TITLE_MAX:
        return text
    cut = text[: TITLE_MAX - 1]
    if " " in cut[TITLE_MAX // 2:]:  # end at a whole word, never mid-word (she would hear half a word)
        cut = cut[: cut.rindex(" ")]
    return cut.rstrip(" ,;:-") + "…"


def parse_feed_titles(content: bytes) -> list[str]:
    """Titles of the entries of an RSS 2.0 or Atom feed, in feed order. A broken feed gives []."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []
    titles = []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag in ("item", "entry"):
            for child in el:
                if child.tag.rsplit("}", 1)[-1] == "title":
                    title = clean_title(child.text)
                    if title:
                        titles.append(title)
                    break
    return titles


def _fetch_feed(link: m.AppLink) -> list[dict[str, str]]:
    try:
        r = http_get(link.value, None, FEED_TIMEOUT_S)
        if r.status_code != 200:
            return []
        return [{"source_label": link.label, "title": t} for t in parse_feed_titles(r.content)[:NEWS_TOP]]
    except Exception:  # noqa: BLE001 - one broken feed must not stop the others
        return []


def _interleave(feeds: list[list[dict[str, str]]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for i in range(NEWS_TOP):
        for feed in feeds:
            if i < len(feed) and len(out) < NEWS_TOP:
                out.append(feed[i])
    return out


@router.get("/media/news")
def news(user_id: int, db: Session = Depends(get_db)) -> list[dict[str, str]]:
    if db.get(m.User, user_id) is None:
        raise HTTPException(404, "user not found")
    links = list(db.scalars(
        select(m.AppLink).where(m.AppLink.user_id == user_id, m.AppLink.kind == "rss").order_by(m.AppLink.sort, m.AppLink.id)
    ))
    if not links:
        return []
    key = (user_id, tuple((link.label, link.value) for link in links))
    hit = _news_cache.get(key)
    if hit is not None and _clock() - hit[0] < NEWS_TTL_S:
        return hit[1]
    with ThreadPoolExecutor(max_workers=len(links)) as pool:
        feeds = list(pool.map(_fetch_feed, links))
    items = _interleave(feeds)
    if items:  # a total failure is not cached: the next ask tries again
        _news_cache[key] = (_clock(), items)
    return items
