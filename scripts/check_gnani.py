import requests
from dotenv import dotenv_values

key = dotenv_values(".env").get("GNANI_API_KEY")
if not key:
    raise SystemExit("GNANI_API_KEY missing in .env")

r = requests.post(
    "https://api.vachana.ai/api/v1/tts/inference",
    headers={"X-API-Key-ID": key, "Content-Type": "application/json"},
    json={"text": "\u0928\u092e\u0938\u094d\u0915\u093e\u0930", "model": "timbre-v2.5", "voice": "Omkar"},
    timeout=30,
)
print("HTTP status:", r.status_code)
print("Content-Type:", r.headers.get("Content-Type"))
if r.status_code != 200:
    print("Body (first 300 chars):", r.text[:300])
