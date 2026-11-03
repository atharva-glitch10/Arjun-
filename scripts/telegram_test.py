"""Send a Telegram test message through the real bot.

Usage:
  python scripts/telegram_test.py           plain test message (direct Telegram API)
  python scripts/telegram_test.py --call    core-api sends a test alert with a family-call join link
                                            for user 1 (core-api must be running, with TELEGRAM_* set)

The bot token and chat id are read from .env and never printed. The join link is a short-lived
bearer credential, so it is not printed either: the script only says whether the button was included.
"""

import sys

import httpx
from dotenv import dotenv_values

env = dotenv_values(".env")
token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
chat = env.get("TELEGRAM_CHAT_ID", "").strip()
if not token or not chat:
    raise SystemExit("Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env first")

if "--call" in sys.argv:
    base = (env.get("CORE_API_URL") or "http://127.0.0.1:8000").rstrip("/")
    key = env.get("CORE_API_KEY", "").strip()
    try:
        res = httpx.post(f"{base}/users/1/alert/test", headers={"X-API-Key": key}, timeout=10)
    except httpx.HTTPError as exc:
        raise SystemExit(f"core-api is not reachable at {base}: {type(exc).__name__}") from exc
    if res.status_code != 200:
        raise SystemExit(f"core-api refused the test alert (HTTP {res.status_code})")
    data = res.json()
    if not data.get("queued"):
        raise SystemExit(f"not sent: {data.get('reason') or 'telegram is off'}")
    if data.get("join_url"):
        print("queued a test alert with a join button")
    else:
        print("queued a test alert (BASE_URL is empty: no join button)")
    raise SystemExit(0)

res = httpx.post(
    f"https://api.telegram.org/bot{token}/sendMessage",
    data={"chat_id": chat, "text": "Arjun test: alerts will arrive here"},
    timeout=10,
)
print("ok" if res.json().get("ok") else f"failed: {res.json().get('description')}")
