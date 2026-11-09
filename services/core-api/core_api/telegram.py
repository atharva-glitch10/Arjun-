"""Free family alerts over Telegram (no SMS provider).

The elder's safety turn must never wait for the network: `claim()` decides and reserves a slot,
`send_alert()` posts from a daemon thread, and the worker records `alert_sent` / `alert_failed` in the
family feed. The bot token and chat id are read from the environment and NEVER logged (the request URL
contains the token, so even the exception text is not logged).

Telegram is off unless TELEGRAM_ENABLED=1 AND both TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set.
One alert per (user, kind) per 10 minutes, counted from the attempt; the "sent recently" wording is
kept separately so a failed send is never reported as sent.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx
from sqlalchemy.orm import sessionmaker

from . import baseurl
from . import models as m
from .db import SessionLocal

log = logging.getLogger("core_api.telegram")

API = "https://api.telegram.org"
DEDUPE_S = 600
BUTTON = "📞 आईशी बोला / Join call"

# The family sees these in Telegram. {name} is the elder's name, without the "(synthetic)" demo tag.
TEXTS: dict[str, str] = {
    "emergency": "🚨 {name}: तातडीची मदत हवी — लगेच संपर्क करा",
    "distress": "⚠️ {name} यांना बरं वाटत नाहीये",
    "request": "📞 {name} यांनी बोलायला सांगितलं आहे",
    "test": "🔔 {name}: हा अर्जुनकडून आलेला एक चाचणी संदेश आहे.",
}

_lock = threading.Lock()
_last_attempt: dict[tuple[int, str], float] = {}
_last_ok: dict[tuple[int, str], float] = {}
_last_failed: dict[tuple[int, str], float] = {}
_threads: set[threading.Thread] = set()
_clock: Callable[[], float] = time.monotonic


def enabled() -> bool:
    return os.environ.get("TELEGRAM_ENABLED", "").strip() == "1"


def configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()) and bool(
        os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    )


def ready() -> bool:
    """True only when alerts are switched on AND have somewhere to go."""
    return enabled() and configured()


def alert_text(kind: str, name: str) -> str:
    return TEXTS.get(kind, TEXTS["test"]).format(name=name)


def claim(user_id: int, kind: str, *, dedupe: bool = True) -> str:
    """Reserve one alert slot. Returns "off", "recent" (inside the 10-minute window) or "ready".

    "ready" also marks the slot, so two simultaneous requests cannot both send. The caller must then
    call `send_alert`. `dedupe=False` is for the manual test message only.
    """
    if not ready():
        return "off"
    if not dedupe:
        return "ready"
    now = _clock()
    key = (user_id, kind)
    with _lock:
        last = _last_attempt.get(key)
        if last is not None and now - last < DEDUPE_S:
            return "recent"
        _last_attempt[key] = now
    return "ready"


def sent_recently(user_id: int, kind: str) -> bool:
    """True only if a message of this kind was actually DELIVERED inside the window."""
    return recent_outcome(user_id, kind) == "sent"


def recent_outcome(user_id: int, kind: str) -> str:
    """What the last attempt of this kind did: "sent", "failed", "pending" (still in flight) or "none"."""
    now = _clock()
    key = (user_id, kind)
    with _lock:
        ok = _last_ok.get(key)
        bad = _last_failed.get(key)
        attempted = _last_attempt.get(key)
    if ok is not None and now - ok < DEDUPE_S:
        return "sent"
    if bad is not None and now - bad < DEDUPE_S:
        return "failed"
    if attempted is not None and now - attempted < DEDUPE_S:
        return "pending"
    return "none"


def send_alert(
    text: str,
    join_url: str | None = None,
    *,
    user_id: int | None = None,
    kind: str = "alert",
    bind: Any = None,
    button_text: str | None = None,
) -> bool:
    """Queue one Telegram message on a daemon thread. False when Telegram is off (nothing is sent).

    `join_url` becomes an inline button that opens the family call. `bind` is the SQLAlchemy engine the
    caller's session uses, so the `alert_sent` / `alert_failed` row lands in the same database.
    """
    if not ready():
        return False
    t = threading.Thread(
        target=_deliver,
        args=(text, join_url, user_id, kind, bind, button_text),
        name="telegram-alert",
        daemon=True,
    )
    with _lock:
        _threads.add(t)
    t.start()
    return True


def _deliver(
    text: str, join_url: str | None, user_id: int | None, kind: str, bind: Any,
    button_text: str | None = None,
) -> None:
    ok = False
    try:
        # a dead / refused BASE_URL must never reach the family as a button (2026-11-09): the alert goes out as text
        join_url, extra = baseurl.guard_link(join_url)
        if extra:
            text = f"{text}\n{extra}"
        ok = _post(text, join_url, button_text)
    except Exception as exc:  # noqa: BLE001 - a network failure must never reach the elder's turn
        # Type only: the exception text can contain the request URL, and that URL contains the bot token.
        log.warning("telegram alert failed: %s", type(exc).__name__)
    if user_id is not None:
        with _lock:
            if ok:
                _last_ok[(user_id, kind)] = _clock()
                _last_failed.pop((user_id, kind), None)
            else:
                _last_failed[(user_id, kind)] = _clock()
        try:
            _record(user_id, ok, bind)
        except Exception as exc:  # noqa: BLE001 - the alert was already attempted
            log.warning("could not record telegram outcome: %s", type(exc).__name__)
    with _lock:
        _threads.discard(threading.current_thread())


def _post(text: str, join_url: str | None, button_text: str | None = None) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    payload: dict[str, Any] = {"chat_id": chat, "text": text}
    if join_url:
        payload["reply_markup"] = {"inline_keyboard": [[{"text": button_text or BUTTON, "url": join_url}]]}
    res = httpx.post(f"{API}/bot{token}/sendMessage", json=payload, timeout=10)
    if res.status_code != 200:
        return False
    try:
        return bool(res.json().get("ok"))
    except ValueError:
        return False


def send_voice(audio: bytes, caption: str) -> bool:
    """Send a generated OGG/Opus voice note without ever logging Telegram's token or request URL."""
    if not ready() or not audio:
        return False
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    try:
        res = httpx.post(
            f"{API}/bot{token}/sendVoice",
            data={"chat_id": chat, "caption": caption},
            files={"voice": ("briefing.ogg", audio, "audio/ogg")},
            timeout=30,
        )
        return res.status_code == 200 and bool(res.json().get("ok"))
    except Exception as exc:  # noqa: BLE001 - request URL contains the bot token
        log.warning("telegram voice delivery failed: %s", type(exc).__name__)
        return False


def _record(user_id: int, ok: bool, bind: Any) -> None:
    kind = "alert_sent" if ok else "alert_failed"
    body = (
        "Telegram alert sent to the family."
        if ok
        else "Telegram alert could not be sent. The family dashboard alert is still here."
    )
    _write(user_id, kind, body, bind)


def _write(user_id: int, kind: str, body: str, bind: Any) -> None:
    """Write one feed line from the worker thread, retrying briefly if SQLite is busy with the request."""
    factory = sessionmaker(bind=bind or SessionLocal, autoflush=False, expire_on_commit=False)
    last: Exception | None = None
    for attempt in range(3):
        try:
            with factory() as db:
                db.add(m.Notification(user_id=user_id, kind=kind, body=body[:300]))
                db.commit()
            return
        except Exception as exc:  # noqa: BLE001 - retry a locked database, then give up
            last = exc
            time.sleep(0.05 * (attempt + 1))
    if last is not None:
        raise last


def wait_idle(timeout: float = 5.0) -> None:
    """Wait for every queued message to finish (tests, and the manual test script)."""
    end = time.monotonic() + timeout
    while True:
        with _lock:
            threads = [t for t in _threads if t.is_alive()]
        if not threads or time.monotonic() >= end:
            return
        for t in threads:
            t.join(timeout=max(0.01, min(0.1, end - time.monotonic())))


def reset_for_tests() -> None:
    wait_idle()
    with _lock:
        _last_attempt.clear()
        _last_ok.clear()
        _last_failed.clear()
        _threads.clear()
