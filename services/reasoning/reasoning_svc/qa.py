"""Pure helpers for "answer any question" (2026-11-09): the search query builder, the facts computed IN CODE from today's
date, friendly source names, and the quality gate that decides whether a drafted answer really answers the question.
No network and no LLM here, so all of it is unit-tested."""

from __future__ import annotations

import re
from datetime import date

from . import langid

_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December")
_YEAR = re.compile(r"\b(19|20)\d{2}\b")


def today_phrase(today: date) -> str:
    return f"{today.day} {_MONTHS[today.month - 1]} {today.year}"


def build_queries(
    llm: dict | None, text: str, today: date, time_sensitive: bool, city: str = ""
) -> list[str]:
    """At most TWO search queries. The model's own English queries first (they fix speech-to-text spellings and add the
    place), else her raw words. A time-sensitive question gets today's date so a search engine prefers fresh pages."""
    raw: list[str] = []
    llm = llm or {}
    for q in list(llm.get("queries") or []) + [llm.get("web_query") or ""]:
        q = " ".join(str(q or "").split())
        if q and q.casefold() not in [x.casefold() for x in raw]:
            raw.append(q[:200])
    if not raw:
        raw = [" ".join(text.split())[:200]]
    out: list[str] = []
    for q in raw[:2]:
        if time_sensitive and not _YEAR.search(q):
            q = f"{q} {today_phrase(today)}"
        out.append(q)
    return out


def reworded(text: str, entity: str, tried: list[str]) -> str | None:
    """A different query for the one retry when the first results were weak: her own words (the original language
    often matches local pages better), with the entity in front. None when that would repeat a query already tried."""
    q = " ".join(f"{entity} {text}".split())[:200] if entity and entity.casefold() not in text.casefold() else " ".join(text.split())[:200]
    return q if q and q.casefold() not in [t.casefold() for t in tried] else None


def weak(results: list[dict] | None) -> bool:
    """True when a search gave nothing usable: no result, or only one very thin one."""
    if not results:
        return True
    return len(results) == 1 and len(str(results[0].get("snippet") or "")) < 80


# ---- facts computed in code ------------------------------------------------------------------------------------
_BORN = re.compile(
    r"born[^0-9A-Za-z]{0,12}(?:on\s+)?(?:(\d{1,2})\s+([A-Z][a-z]+)\s+(\d{4})|([A-Z][a-z]+)\s+(\d{1,2}),?\s+(\d{4}))"
)


def _month(name: str) -> int | None:
    for i, m in enumerate(_MONTHS, 1):
        if m.lower().startswith(name.lower()[:3]) and len(name) >= 3:
            return i
    return None


def computed_facts(texts: list[str], today: date) -> str:
    """Ages worked out HERE from a birth date found in the results and today's date, so an old article's "aged 71" can
    never be repeated as if it were current. Returns a line for the prompt, or ""."""
    for blob in texts:
        m = _BORN.search(blob or "")
        if not m:
            continue
        day, mon, year = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(5), m.group(4), m.group(6))
        month = _month(mon)
        if not month:
            continue
        try:
            born = date(int(year), month, int(day))
        except ValueError:
            continue
        years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        if 0 <= years <= 125:
            return (f"COMPUTED IN CODE (trust this, not article text): born {born.day} {_MONTHS[born.month - 1]} "
                    f"{born.year}, so on {today_phrase(today)} the age is {years} years.")
    return ""


# ---- friendly source names ---------------------------------------------------------------------------------------
_SOURCES = {
    "bbc.com": "BBC", "bbc.co.uk": "BBC", "wikipedia.org": "Wikipedia", "espncricinfo.com": "ESPNcricinfo",
    "cricbuzz.com": "Cricbuzz", "timesofindia.indiatimes.com": "Times of India", "indiatimes.com": "Times of India",
    "thehindu.com": "The Hindu", "ndtv.com": "NDTV", "hindustantimes.com": "Hindustan Times", "reuters.com": "Reuters",
    "britannica.com": "Britannica", "lokmat.com": "Lokmat", "loksatta.com": "Loksatta", "goodreturns.in": "GoodReturns",
    "moneycontrol.com": "Moneycontrol", "nasa.gov": "NASA",
}


def source_name(domain: str) -> str:
    d = (domain or "").lower().removeprefix("www.")
    for k, v in _SOURCES.items():
        if d == k or d.endswith("." + k):
            return v
    parts = d.split(".")
    base = parts[-3] if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "gov", "ac") else (parts[-2] if len(parts) >= 2 else d)
    return base.capitalize() if base else ""


# ---- the quality gate ----------------------------------------------------------------------------------------------
_OWN_SCRIPT = {
    "mr": (0x0900, 0x097F), "hi": (0x0900, 0x097F), "bn": (0x0980, 0x09FF), "pa": (0x0A00, 0x0A7F),
    "gu": (0x0A80, 0x0AFF), "ta": (0x0B80, 0x0BFF), "te": (0x0C00, 0x0C7F), "kn": (0x0C80, 0x0CFF),
    "ml": (0x0D00, 0x0D7F),
}
# a question that asks for a NUMBER (how many / how much / when / what price / score / age)
_ASKS_NUMBER = re.compile(
    r"how\s+(?:many|much|old|long|far|tall)|what\s+(?:time|year|date|price|score|temperature)|\bwhen\b|\bprice\b|\bscore\b|"
    r"\brate\b|किती|कधी|भाव|दर\b|स्कोर|वय\b|कितना|कितने|कितनी|कब\b|उम्र|कीमत|तापमान|"
    r"எத்தனை|எவ்வளவு|எப்போது|ఎంత|ఎన్ని|ఎప్పుడు|ಎಷ್ಟು|ಯಾವಾಗ|എത്ര|എപ്പോൾ|কত|কখন|કેટલા|ક્યારે|ਕਿੰਨੇ|ਕਦੋਂ",
    re.IGNORECASE,
)
_HAS_NUMBER = re.compile(r"[0-9०-९০-৯૦-૯੦-੯௦-௯౦-౯೦-೯൦-൯]|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
                         r"hundred|thousand|lakh|crore|million|billion|first|second|third)\b|"
                         r"(?<!\S)(?:एक|दोन|तीन|चार|पाच|सहा|सात|आठ|नऊ|दहा|अकरा|बारा|वीस|तीस|पन्नास|शंभर|हजार|लाख|कोटी|दो|पांच|पाँच|छह|छः|नौ|दस|सौ|हज़ार)(?!\S)",
                         re.IGNORECASE)
_UNSURE = re.compile(
    r"not sure|i could not|couldn't|खात्री नाही|पक्का नाही|पक्के तौर पर नहीं|निश्चित नहीं|नक्की नाही|माहिती मिळाली नाही|जानकारी नहीं मिली|"
    r"உறுதியாக|నిశ్చయంగా|ಖಚಿತವಿಲ್ಲ|ഉറപ്പില്ല|নিশ্চিত নই|ખાતરી નથી|ਪੱਕਾ ਨਹੀਂ",
    re.IGNORECASE,
)
_GENERIC = re.compile(
    r"^(?:ok(?:ay)?|sure|i can help(?: you)? with that|let me (?:see|check)|ठीक आहे|ठीक है|सांगा|बोला)[.!… ]*$", re.IGNORECASE
)


def _letters(text: str) -> list[str]:
    return [c for c in text if c.isalpha()]


def in_her_language(reply: str, lang: str) -> bool:
    """Most of the letters are in her script (a few Latin names are fine); English must be mostly Latin."""
    letters = _letters(reply)
    if not letters:
        return False
    if lang in _OWN_SCRIPT:
        lo, hi = _OWN_SCRIPT[lang]
        return sum(1 for c in letters if lo <= ord(c) <= hi) / len(letters) >= 0.4
    return sum(1 for c in letters if ord(c) < 0x250) / len(letters) >= 0.7


def answers_question(question: str, reply: str, lang: str) -> tuple[bool, str]:
    """(ok, why-not). Cheap structural checks, no model: the reply is non-empty and not boilerplate, is in her language,
    and when she asked for a number/time/price/score it contains one (or honestly says it is not sure)."""
    reply = (reply or "").strip()
    if len(reply) < 3 or _GENERIC.match(reply):
        return False, "empty_or_generic"
    if not in_her_language(reply, lang) or not langid.matches(reply, lang):  # also Hindi vs Marathi (both Devanagari)
        return False, "wrong_language"
    if reply.endswith(("?", "？")):
        return True, ""  # a clarifying question naming the options is a valid answer to an ambiguous question
    if _ASKS_NUMBER.search(question or "") and not _HAS_NUMBER.search(reply) and not _UNSURE.search(reply):
        return False, "no_number"
    return True, ""
