"""Apps and links the family lets Arjun open by voice (YouTube, news feeds, WhatsApp, web links).

Everything the elder can open comes from this table, never from the LLM: the family adds it, the values are
validated here (https only, known hosts unless the family explicitly approves another one), and reasoning only
chooses among the rows. WhatsApp rows point at an existing contact; phone numbers stay in `contacts`.
"""

import re
from typing import Literal
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .db import get_db
from .deps import require_key

Kind = Literal[
    "youtube_query", "youtube_video", "youtube_playlist", "youtube_channel_live", "youtube_live",
    "rss", "whatsapp", "link"
]
# "youtube_live" is the short name a caller may send; the stored/played kind is the channel-live one the screen knows.
_CANONICAL = {"youtube_live": "youtube_channel_live"}

YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")
# Hosts that need no warning. A suffix match: "marathi.abplive.com" is "abplive.com".
KNOWN_HOSTS = YOUTUBE_HOSTS + (
    "wa.me", "photos.google.com", "photos.app.goo.gl",
    "loksatta.com", "lokmat.com", "maharashtratimes.com", "esakal.com", "abplive.com", "tv9marathi.com",
    "zeenews.india.com", "news18.com", "ndtv.com", "thehindu.com", "indianexpress.com", "hindustantimes.com",
    "indiatimes.com", "bbc.com", "bbci.co.uk", "pib.gov.in", "ddnews.gov.in", "prabhatkhabar.com",
)

_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_PLAYLIST_ID = re.compile(r"^[A-Za-z0-9_-]{12,64}$")
_CHANNEL_ID = re.compile(r"^UC[A-Za-z0-9_-]{22}$")


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def host_is_known(host: str) -> bool:
    return any(host == h or host.endswith("." + h) for h in KNOWN_HOSTS)


def https_url(value: str) -> str:
    """The URL if it is a plain https web address; else ValueError. No http, no userinfo, no IP literals."""
    url = value.strip()
    parts = urlparse(url)
    if parts.scheme != "https":
        raise ValueError("only https links are allowed")
    host = (parts.hostname or "").lower()
    if not host or "." not in host or parts.username or parts.password:
        raise ValueError("not a valid web address")
    if host == "localhost" or host.endswith((".local", ".internal")) or re.fullmatch(r"[\d.]+|[0-9a-f:]+", host):
        raise ValueError("local and numeric addresses are not allowed")
    return url


def _query_param(url: str, name: str) -> str | None:
    values = parse_qs(urlparse(url).query).get(name)
    return values[0] if values else None


def normalise_value(kind: str, value: str, allow_other_host: bool) -> tuple[str, bool]:
    """(clean value, True when the host is NOT on the allowlist but the family approved it). Raises ValueError."""
    value = value.strip()
    if kind == "youtube_query":
        if not 1 <= len(value) <= 100 or value.lower().startswith(("http:", "https:")):
            raise ValueError("a YouTube search is a few words, not a link")
        return value, False
    if kind == "youtube_video":
        if value.startswith("http"):
            url = https_url(value)
            host = host_of(url)
            if host == "youtu.be":
                value = urlparse(url).path.strip("/")
            elif host.endswith("youtube.com"):
                value = _query_param(url, "v") or ""
            else:
                value = ""
        if not _VIDEO_ID.match(value):
            raise ValueError("not a YouTube video id")
        return value, False
    if kind == "youtube_playlist":
        if value.startswith("http"):
            url = https_url(value)
            value = (_query_param(url, "list") or "") if host_of(url).endswith("youtube.com") else ""
        if not _PLAYLIST_ID.match(value):
            raise ValueError("not a YouTube playlist id")
        return value, False
    if kind == "youtube_channel_live":
        if value.startswith("http"):
            url = https_url(value)
            found = re.search(r"/channel/(UC[A-Za-z0-9_-]{22})", urlparse(url).path)
            value = (found.group(1) if found else _query_param(url, "channel")) or ""
        if not _CHANNEL_ID.match(value):
            raise ValueError("not a YouTube channel id (it starts with UC)")
        return value, False
    if kind in ("rss", "link"):
        url = https_url(value)
        if host_is_known(host_of(url)):
            return url, False
        if not allow_other_host:
            raise ValueError("this website is not on the known list; the family must approve it explicitly")
        return url, True
    raise ValueError("unknown kind")  # whatsapp is checked against contacts by the endpoint


class AppLinkIn(BaseModel):
    kind: Kind
    label: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=500)
    spoken_names: list[str] = Field(default_factory=list, max_length=10)
    sort: int = 0
    allow_other_host: bool = False


class AppLinkPatch(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=100)
    value: str | None = Field(default=None, min_length=1, max_length=500)
    spoken_names: list[str] | None = Field(default=None, max_length=10)
    sort: int | None = None
    allow_other_host: bool = False


class AppLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    label: str
    value: str
    spoken_names: list[str]
    sort: int
    other_host: bool  # the dashboard shows a warning for these
    approved_by_family: bool  # same fact, the name the family dashboard uses


router = APIRouter(dependencies=[Depends(require_key)])


def _names(names: list[str]) -> list[str]:
    """Lower-cased spoken names, de-duplicated, at most 10 (the elder says them; matching is never case-sensitive)."""
    seen: list[str] = []
    for n in names:
        n = n.strip().lower()[:60]
        if n and n not in seen:
            seen.append(n)
    return seen[:10]


def _check(db: Session, user_id: int, kind: str, value: str, allow_other: bool) -> tuple[str, bool]:
    if db.get(m.User, user_id) is None:
        raise HTTPException(404, "user not found")
    if kind == "whatsapp":
        contact = db.get(m.Contact, int(value)) if value.strip().isdigit() else None
        if contact is None or contact.user_id != user_id:
            raise HTTPException(422, "a WhatsApp entry must point at one of her contacts (use the contact id)")
        return str(contact.id), False
    try:
        return normalise_value(kind, value, allow_other)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/users/{user_id}/app-links", response_model=list[AppLinkOut])
@router.get("/users/{user_id}/apps", response_model=list[AppLinkOut])
def list_app_links(user_id: int, db: Session = Depends(get_db)) -> list[m.AppLink]:
    if db.get(m.User, user_id) is None:
        raise HTTPException(404, "user not found")
    q = select(m.AppLink).where(m.AppLink.user_id == user_id).order_by(m.AppLink.sort, m.AppLink.id)
    return list(db.scalars(q))


@router.post("/users/{user_id}/app-links", response_model=AppLinkOut, status_code=201)
@router.post("/users/{user_id}/apps", response_model=AppLinkOut, status_code=201)
def add_app_link(user_id: int, body: AppLinkIn, db: Session = Depends(get_db)) -> m.AppLink:
    kind = _CANONICAL.get(body.kind, body.kind)
    value, other = _check(db, user_id, kind, body.value, body.allow_other_host)
    row = m.AppLink(
        user_id=user_id, kind=kind, label=body.label.strip(), value=value,
        spoken_names=_names(body.spoken_names), sort=body.sort, other_host=other,
    )
    db.add(row)
    db.commit()
    return row


def _row(db: Session, user_id: int, link_id: int) -> m.AppLink:
    row = db.get(m.AppLink, link_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(404, "link not found")
    return row


@router.patch("/users/{user_id}/app-links/{app_id}", response_model=AppLinkOut)
@router.patch("/users/{user_id}/apps/{app_id}", response_model=AppLinkOut)
def patch_app_link(user_id: int, app_id: int, body: AppLinkPatch, db: Session = Depends(get_db)) -> m.AppLink:
    row = _row(db, user_id, app_id)
    if body.value is not None:
        row.value, row.other_host = _check(db, user_id, row.kind, body.value, body.allow_other_host)
    if body.label is not None:
        row.label = body.label.strip()
    if body.spoken_names is not None:
        row.spoken_names = _names(body.spoken_names)
    if body.sort is not None:
        row.sort = body.sort
    db.commit()
    return row


@router.delete("/users/{user_id}/app-links/{app_id}", status_code=204)
@router.delete("/users/{user_id}/apps/{app_id}", status_code=204)
def delete_app_link(user_id: int, app_id: int, db: Session = Depends(get_db)) -> None:
    db.delete(_row(db, user_id, app_id))
    db.commit()


# ---- "did she just name one of the family's apps?" ------------------------------------------------------------
# Split on punctuation only: Devanagari vowel signs and the virama are part of a word and must stay in it.
_PUNCT = re.compile(r"[,.?!।;:\"'“”‘’()\[\]{}…–—-]+")


def _words(text: str) -> list[str]:
    return _PUNCT.sub(" ", text.lower()).split()


@router.get("/users/{user_id}/apps/match", response_model=AppLinkOut | None)
def match_app(user_id: int, q: str, db: Session = Depends(get_db)) -> m.AppLink | None:
    """The family's best app whose label or spoken name appears whole in `q`, or null (never a guess).

    Whole-word after the same normalisation reasoning uses: lower-case, Devanagari kept, punctuation dropped.
    The most specific (longest) name wins; ties follow the family's sort order.
    """
    if db.get(m.User, user_id) is None:
        raise HTTPException(404, "user not found")
    said = set(_words(q))
    best: m.AppLink | None = None
    best_len = 0
    for row in db.scalars(
        select(m.AppLink).where(m.AppLink.user_id == user_id).order_by(m.AppLink.sort, m.AppLink.id)
    ):
        for name in [row.label, *row.spoken_names]:
            words = _words(name)
            if words and len(words) > best_len and all(w in said for w in words):
                best, best_len = row, len(words)
    return best
