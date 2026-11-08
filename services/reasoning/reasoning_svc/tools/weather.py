"""Weather from Open-Meteo (no API key). `current_weather(city, lang)` returns one spoken sentence or None."""

from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger("arjun.weather")

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_S = 3.0
_geo: dict[str, tuple[float, float]] = {}

_SKY = {
    "mr": {"clear": "आकाश स्वच्छ आहे", "cloud": "ढगाळ आहे", "fog": "धुकं आहे", "rain": "पाऊस आहे", "storm": "वादळी पाऊस आहे"},
    "hi": {"clear": "आसमान साफ़ है", "cloud": "बादल हैं", "fog": "कोहरा है", "rain": "बारिश हो रही है", "storm": "आंधी-बारिश है"},
    "en": {"clear": "the sky is clear", "cloud": "it is cloudy", "fog": "it is foggy", "rain": "it is raining", "storm": "there is a thunderstorm"},
}
_FMT = {
    "mr": "{city}मध्ये आत्ता {sky}, तापमान {temp} अंश. आज {low} ते {high} अंश, पावसाची शक्यता {rain} टक्के.",
    "hi": "{city} में अभी {sky}, तापमान {temp} डिग्री। आज {low} से {high} डिग्री, बारिश की संभावना {rain} प्रतिशत।",
    "en": "In {city} right now {sky}, {temp} degrees. Today {low} to {high}, chance of rain {rain} percent.",
}


def _group(code: int) -> str:
    """WMO weather code -> the few sky groups that matter to an elder."""
    if code in (0, 1):
        return "clear"
    if code in (45, 48):
        return "fog"
    if code >= 95:
        return "storm"
    if code >= 51:
        return "rain"
    return "cloud"


def current_weather(city: str, lang: str = "mr", client: httpx.Client | None = None) -> str | None:
    city = " ".join((city or "").split())[:80]
    if not city:
        return None
    http = client or httpx.Client(timeout=TIMEOUT_S)
    try:
        spot = _geo.get(city.casefold())
        if spot is None:
            r = http.get(GEO_URL, params={"name": city, "count": 1, "country_code": "IN"}, timeout=TIMEOUT_S)
            r.raise_for_status()
            found = (r.json().get("results") or [None])[0]
            if not found:
                return None
            spot = (float(found["latitude"]), float(found["longitude"]))
            _geo[city.casefold()] = spot
        r = http.get(
            FORECAST_URL,
            params={
                "latitude": spot[0], "longitude": spot[1], "timezone": "auto", "forecast_days": 1,
                "current": "temperature_2m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            },
            timeout=TIMEOUT_S,
        )
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        cur, day = data["current"], data["daily"]
        sky = _SKY.get(lang, _SKY["en"])[_group(int(cur["weather_code"]))]
        rain = day["precipitation_probability_max"][0]
        return _FMT.get(lang, _FMT["en"]).format(
            city=city, sky=sky, temp=round(cur["temperature_2m"]),
            low=round(day["temperature_2m_min"][0]), high=round(day["temperature_2m_max"][0]),
            rain=round(rain if rain is not None else 0),
        )
    except Exception as exc:  # noqa: BLE001 - weather must never break a turn
        log.info("weather failed: %s", type(exc).__name__)
        return None
    finally:
        if client is None:
            http.close()
