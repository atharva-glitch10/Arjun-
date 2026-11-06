"""Safely inspect Gnani key presence and configured models without making API calls."""

from pathlib import Path

from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
values = dotenv_values(root / ".env") if (root / ".env").is_file() else {}
key = values.get("GNANI_API_KEY")
if key is None:
    print("GNANI_API_KEY: missing")
else:
    print(f"GNANI_API_KEY: present={bool(key.strip())}; whitespace={'yes' if key != key.strip() else 'no'}")

print("STT integration: pinned livekit-plugins-gnani 1.8.6 (model selected internally by plugin)")
print(f"STT format: {values.get('GNANI_STT_FORMAT') or 'transcribe'}")
print(f"STT language hint: {values.get('GNANI_STT_LANGUAGE') or 'mr-IN'}")
print(f"STT streaming: {values.get('GNANI_USE_STREAMING') or '1'}")
print(f"TTS model: {values.get('GNANI_TTS_MODEL') or 'timbre-v3.0'}")
print(f"TTS voice: {values.get('GNANI_TTS_VOICE') or 'Avinash'}")
print("No network request was made; API authentication is not verified by this diagnostic.")
