import httpx
from dotenv import dotenv_values

e = dotenv_values(".env")
token, chat = e.get("TELEGRAM_BOT_TOKEN", ""), e.get("TELEGRAM_CHAT_ID", "")
if not token or not chat:
    raise SystemExit("Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env first")
r = httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
               data={"chat_id": chat, "text": "Arjun test: alerts will arrive here"}, timeout=10)
print("ok" if r.json().get("ok") else f"failed: {r.json().get('description')}")
