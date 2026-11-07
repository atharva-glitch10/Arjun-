"""Fires due reminders and medicine prompts via core-api, which QUEUES each one for delivery (T8).

All state is in core-api (SQL). This process only polls and triggers.

A queued item is spoken by an open voice session (the agent pulls it from the queue). "fired" in core-api
still only means "the due time passed"; only a delivery with `spoken_at` was heard. Each tick ends with a
sweep that retires finished items, applies the late / backlog rules and tells the family about items that
could not be spoken on time.

Daily voice briefings are sent by core-api at BRIEFING_TIME; openers remain a separate reasoning flow.
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

CORE = os.environ.get("CORE_API_URL", "http://core-api:8000")
REASONING = os.environ.get("REASONING_URL", "http://reasoning:8001")
KEY = os.environ.get("CORE_API_KEY", "")
INTERVAL = int(os.environ.get("SCHEDULER_INTERVAL_SECONDS", "30"))
OPENER_USER_IDS = [int(x) for x in os.environ.get("OPENER_USER_IDS", "").split(",") if x.strip()]

log = logging.getLogger("scheduler")
# In-memory only: a scheduler RESTART forgets these, so a second opener/briefing can happen the same
# day. Known limitation; core-api's decline gate still blocks openers after "nako".
_opened_today: dict[int, str] = {}  # user_id -> ISO date; at most one opener per day


def today_local() -> str:
    """ISO date in the household timezone (containers run in UTC)."""
    name = os.environ.get("ARJUN_TZ", "Asia/Kolkata")
    try:
        zone = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        zone = timezone(timedelta(hours=5, minutes=30)) if name == "Asia/Kolkata" else None
    return datetime.now(zone).date().isoformat()


def tick(http: httpx.Client, today: str) -> list[dict[str, object]]:
    opener_ids = OPENER_USER_IDS
    if not opener_ids:
        try:  # empty opener list means every user with daily check-ins on
            ids = [int(x) for x in http.get(f"{CORE}/internal/checkin-users").json()]
            opener_ids = opener_ids or ids
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            log.warning("could not read the check-in users (opener stays empty): %s", type(exc).__name__)
    fired = http.post(f"{CORE}/internal/reminders/fire-due").json()
    for item in fired:
        log.info("reminder due, queued for delivery user=%s task=%s", item["user_id"], item["task"])
    meds = http.post(f"{CORE}/internal/medicines/tick").json()
    for item in meds.get("reminded", []):
        # Queued for delivery by core-api; a voice session speaks it. Name/dose are SQL text, logged verbatim.
        log.info(
            "medicine due, queued for delivery user=%s %s %s (reminder %s)",
            item["user_id"], item["name"], item["dose"], item["reminder_no"],
        )
    for item in meds.get("unconfirmed", []):
        log.info("medicine unconfirmed user=%s %s -> family notified", item["user_id"], item["name"])
    checkins = http.post(f"{CORE}/internal/checkins/tick").json()
    for item in checkins.get("asked", []):
        log.info("check-in due, queued for delivery user=%s %s", item["user_id"], item["kind"])
    for item in checkins.get("followed_up", []):
        log.info("check-in follow-up, queued for delivery user=%s %s", item["user_id"], item["kind"])
    try:  # retire finished items, apply the late / backlog rules, tell the family about undelivered ones
        swept = http.post(f"{CORE}/internal/deliveries/sweep")
        swept.raise_for_status()
        if any(swept.json().values()):
            log.info("delivery sweep: %s", swept.json())
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("delivery sweep failed (the rest of the tick still runs): %s", exc)
    try:  # conversations quiet for a few minutes -> one summary line each for the family dashboard
        flushed = http.post(f"{REASONING}/conversations/flush-idle")
        flushed.raise_for_status()
        if flushed.json().get("sent"):
            log.info("conversation summaries sent: %s", flushed.json()["sent"])
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("conversation flush failed (the rest of the tick still runs): %s", exc)
    try:  # core-api enforces BRIEFING_TIME and the persistent per-user/day dedupe
        response = http.post(f"{CORE}/internal/briefings/send-due")
        response.raise_for_status()
        outcomes = response.json()
        if outcomes.get("sent") or outcomes.get("failed"):
            log.info("daily briefing delivery: sent=%s failed=%s", outcomes.get("sent"), outcomes.get("failed"))
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("daily briefing sweep failed: %s", type(exc).__name__)
    for uid in opener_ids:
        if _opened_today.get(uid) == today:
            continue
        text = http.post(f"{REASONING}/opener/{uid}").json().get("text")
        if text:
            _opened_today[uid] = today
            log.info("opener user=%s: %s", uid, text)  # logged only; voice delivery is T8
    return fired  # type: ignore[no-any-return]


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    headers = {"X-API-Key": KEY} if KEY else {}
    with httpx.Client(headers=headers, timeout=10.0) as http:
        while True:
            try:
                tick(http, today_local())
            except httpx.HTTPError as exc:
                log.warning("tick failed: %s", exc)
            time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
