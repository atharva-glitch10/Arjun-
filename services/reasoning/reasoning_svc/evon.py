"""Client for self-hosted Evon (OpenAI-compatible vLLM/SGLang endpoint).

Contract: strict JSON out, validated against shared/schemas/intent.json. Invalid JSON or schema
failure -> retry once -> caller falls back to the rule-based parser. The LLM never writes to the DB.
"""

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import jsonschema

from . import config

log = logging.getLogger("arjun.llm")

# Debug for the voice path: one redacted JSON line per LLM call and per turn, written only when
# ARJUN_LLM_DEBUG=1. Off by default: the normal log line never carries her words or the reply.
_PHONE = re.compile(r"(?<!\d)(?:\+?91[-\s]?)?[6-9]\d{9}(?!\d)")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_TOKEN = re.compile(r"\b(?:sk|key|tok)[-_][A-Za-z0-9_-]{8,}\b", re.IGNORECASE)


def llm_debug_enabled() -> bool:
    return os.environ.get("ARJUN_LLM_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")


def redact(value: Any) -> Any:
    """Redact phone numbers, e-mail addresses and token-shaped strings before anything is logged."""
    if isinstance(value, str):
        return _TOKEN.sub("[token]", _EMAIL.sub("[email]", _PHONE.sub("[number]", value)))
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    return value


def debug_log(event: str, **fields: Any) -> None:
    """Opt-in (ARJUN_LLM_DEBUG=1) redacted debug line on the arjun.llm logger."""
    if not llm_debug_enabled():
        return
    log.info(json.dumps({"debug": event, **redact(fields)}, ensure_ascii=False, default=str))

_LANG_NAMES = {
    "mr": ("Marathi", "Devanagari"),
    "hi": ("Hindi", "Devanagari"),
    "en": ("English", "Latin"),
    "bn": ("Bengali", "Bengali"), "gu": ("Gujarati", "Gujarati"),
    "kn": ("Kannada", "Kannada"), "ml": ("Malayalam", "Malayalam"),
    "pa": ("Punjabi", "Gurmukhi"), "ta": ("Tamil", "Tamil"),
    "te": ("Telugu", "Telugu"), "or": ("Odia", "Odia"),
}


# ---- what the companion may NOT say: the narrow safety net on top of the prompt --------------------------
# New contract (2026-11-04): reject ONLY medical advice / diagnosis, a claim to be human or to have a body or
# family, Latin script when the turn is Marathi/Hindi, more than four sentences, or more than 300 characters.
# Everything else (brevity, no guilt) is the prompt's job; the sanitizer must not throw
# away a useful, slightly longer answer.
_VIOLATIONS: dict[str, re.Pattern[str]] = {
    # claims to be human, or to have a family / body
    "human": re.compile(
        r"\b(i am|i'm|im)\s+(a\s+)?(real\s+)?(human|person|man|woman|boy|girl)\b"
        r"|मी\s+(एक\s+)?(खरा\s+)?(माणूस|मनुष्य|इंसान|आदमी)\s+(आहे|आहेत|हूँ|हूं)"
        r"|मैं\s+(एक\s+)?(इंसान|इन्सान|आदमी)\s+(हूँ|हूं)"
        r"|\bmy\s+(wife|husband|son|daughter|mother|father|family)\b"
        r"|माझी\s+(बायको|आई|मुलगी|बहीण)|माझा\s+(मुलगा|भाऊ|नवरा)",
        re.IGNORECASE,
    ),
    # medical advice: doses, "take the tablet", rest / water / doctor instructions, a diagnosis
    "medical": re.compile(
        r"\b\d+(\.\d+)?\s*(mg|ml|mcg)\b"
        r"|(गोळी|गोळ्या|औषध|औषधं|दवा|दवाई|टॅबलेट)\s*(घ्या|घे|घेत|खा|लो|खाओ|बंद|वाढवा)"
        r"|\b(take|taking|stop|skip|double)\b.{0,25}\b(tablet|tablets|pill|pills|medicine|medication|dose)\b"
        r"|\byou\s+should\s+(take|stop)\b"
        r"|पडून\s+रा[हह]\S*|झोपून\s+रा[हह]\S*|विश्रांती\s+(?:घ्या|घे)\S*|आराम\s+(?:करा|कर|घ्या|कीजिए|कीजिये|करें|करो)"
        r"|पाणी\s+(?:प्या|पी)\S*|पानी\s+(?:पी|पि)\S*"
        r"|(?:दवा|दवाई|गोली)\s+(?:ले|लें|लीजिए|खा)\S*"
        r"|डॉक्टर(?:कडे|ांकडे|च्याकडे)\s+(?:\S+\s+)?(?:जा|जाच|जावं|जावे|जाऊन)(?=[\s,.!?।]|$)"
        r"|डॉक्टर\s+(?:के\s+पास|को)\s+(?:\S+\s+)?(?:जा|दिखा|मिल)\S*"
        r"|\b(?:you\s+should|please|try\s+to|better)\s+(?:\w+\s+)?(?:rest|lie\s+down)\b|\blie\s+down\b|\btake\s+(?:a|some)\s+rest\b"
        r"|\bdrink\s+(?:some\s+|a\s+glass\s+of\s+|plenty\s+of\s+)?water\b|\bstay\s+hydrated\b"
        r"|\b(?:go|see|visit|consult)\s+(?:and\s+)?(?:see\s+)?(?:a|your|the)\s+(?:doctor|hospital)\b"
        r"|दवाखान्यात\s+(?:\S+\s+)?जा\S*|झोप\s+(?:घ्या|घे)\S*"
        r"|\btake\s+rest\b|\bsee\s+a\s+doctor\b",
        re.IGNORECASE,
    ),
    "unsafe": re.compile(
        r"\b(?:kill yourself|hurt yourself|take your life|you should die|kill (?:him|her|them)|hurt (?:him|her|them))\b"
        r"|स्वतःला\s+(?:मारून\s+टाका|इजा\s+करा)|मरून\s+जा|त्याला\s+मारून\s+टाका"
        r"|खुद\s+को\s+मारो|जान\s+दे\s+दो|उसे\s+मार\s+दो",
        re.IGNORECASE,
    ),
}
_MAX_SENTENCES = 4  # more than four sentences is a runaway; a how-to may use three


def _stated_rest_plan(text: str) -> bool:
    return bool(re.search(r"(?:आराम\s+(?:करते|करतो|करणार|करायचं)|विश्रांती\s+(?:घेते|घेतो|घेणार|घ्यायची)|झोप(?:णार|ायला))", text))


def companion_violations(text: str, language: str, user_text: str = "") -> list[str]:
    """Names of the boundaries a companion reply breaks (empty = fine). Heuristic, not a proof."""
    reasons = [name for name, rx in _VIOLATIONS.items() if rx.search(text)]
    # Agreeing with her own stated plan to rest is not unsolicited health advice.
    if "medical" in reasons and _stated_rest_plan(user_text) and re.search(r"आराम|विश्रांती|झोप", text):
        rest_only = re.sub(r"आराम\s+(?:करा|कर|घ्या)|विश्रांती\s+(?:घ्या|करा)|झोपून\s+राहा", "", text)
        if not _VIOLATIONS["medical"].search(rest_only):
            reasons.remove("medical")
    if language in ("mr", "hi") and not any("\u0900" <= ch <= "\u097f" for ch in text):
        reasons.append("script")  # asked for Devanagari, got Latin
    elif language in _LANG_NAMES and language not in ("mr", "hi", "en"):
        ranges = {"bn": ("\u0980", "\u09ff"), "gu": ("\u0a80", "\u0aff"), "pa": ("\u0a00", "\u0a7f"),
                  "or": ("\u0b00", "\u0b7f"), "ta": ("\u0b80", "\u0bff"), "te": ("\u0c00", "\u0c7f"),
                  "kn": ("\u0c80", "\u0cff"), "ml": ("\u0d00", "\u0d7f")}
        low, high = ranges[language]
        if not any(low <= ch <= high for ch in text):
            reasons.append("script")
    if len(re.split(r"(?<=[.?!।])\s+", text.strip())) > _MAX_SENTENCES:
        reasons.append("sentences")
    return reasons


# Leading fillers the model likes to open with ("मला वाटतं ...", "अरेरे", "वा, छान"). A lookahead, NOT \b: \b fails right
# after a Devanagari vowel sign such as "ं". Longest first, so "मला वाटतं" is not cut at "मला".
_FILLERS = (
    "मला वाटतं", "मला वाटते", "मला वाटतंय", "मला वाटतय", "मला समजलं", "मला समजले", "मला कळलं", "मला आनंद झाला",
    "मुझे लगता है", "अरेरे", "अरे वा", "वा", "ओह", "अच्छा", "बरं", "हो", "हां", "ठीक आहे",
    "का", "अहो", "i think", "i feel", "i understand", "i see", "oh", "wow", "okay", "ok", "sure",
)
_FILLER_RX = re.compile(
    r"^[\s,.!?।-]*(?:" + "|".join(re.escape(f) for f in sorted(_FILLERS, key=len, reverse=True)) + r")(?=[\s,.!?।-]|$)",
    re.IGNORECASE,
)


def strip_filler(text: str, user_text: str = "") -> str:
    """Remove leading fillers and opinion openers, repeatedly, from the START only."""
    out = text.strip()
    while True:
        if _stated_rest_plan(user_text) and re.match(r"^हो[\s,.!?à¥¤-]+", out):
            return out.lstrip(" ,.!?à¥¤-")  # preserve agreement with her stated plan
        cut = _FILLER_RX.sub("", out, count=1)
        if cut == out:
            return out.lstrip(" ,.!?।-")
        out = cut.lstrip(" ,.!?।-")


def sanitize_companion(text: str | None, language: str, user_text: str = "") -> tuple[str | None, list[str]]:
    """Strip leading fillers, then reject the reply if it breaks a narrow boundary.

    Keeps up to four sentences so a how-to answer can use three; never cuts by character count alone.
    """
    if not text or not text.strip():
        debug_log("sanitize", verdict="rejected", reasons=["empty"], text=text)
        return None, ["empty"]
    text = strip_filler(text, user_text)
    if not text:
        debug_log("sanitize", verdict="rejected", reasons=["empty"], text=text)
        return None, ["empty"]
    cut = text.strip()
    reasons = companion_violations(cut, language, user_text)
    if reasons == ["medical"] and language == "mr" and _stated_rest_plan(user_text) and re.search(r"आराम|विश्रांती|झोप", cut):
        return "हो, आराम करा, नंतर बोलूया.", []  # keep only agreement with her plan; discard extra advice
    if reasons:
        debug_log("sanitize", verdict="rejected", reasons=reasons, text=text)
        return None, reasons
    debug_log("sanitize", verdict="ok", reasons=[], text=text, out=cut)
    return cut, []


def salvage_companion(text: str, language: str, user_text: str = "") -> str | None:
    """A reply with ONE bad sentence ("... आराम करा.") should not be thrown away whole: keep the sentences that break no
    boundary. None when nothing usable is left (the fixed line then answers)."""
    parts = [p.strip() for p in re.findall(r"[^।.!?]+[।.!?]*", text) if p.strip()]
    kept = [p for p in parts if not companion_violations(p, language, user_text)]
    if not kept or len(kept) == len(parts):
        return None
    reply, _ = sanitize_companion(" ".join(kept), language, user_text)
    return reply


_LEADING_TAGS = re.compile(r"^((?:\s*<\s*[a-z][a-z ]{1,20}\s*>)*)\s*(.*)$", re.IGNORECASE | re.DOTALL)


def strip_filler_voiced(voiced: str, user_text: str = "") -> str:
    """strip_filler for the TTS text: the leading voice tags stay, the filler after them goes."""
    m = _LEADING_TAGS.match(voiced.strip())
    tags, rest = (m.group(1).strip(), m.group(2)) if m else ("", voiced)
    rest = strip_filler(rest, user_text)
    return f"{tags} {rest}".strip() if tags else rest


# ---- Sarvam "thinking" output -------------------------------------------------------------------------------
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_thinking(text: str | None) -> str | None:
    """Drop reasoning traces ("<think>...</think>") so they are never spoken or shown. An unclosed <think>
    means the answer never came (max_tokens used up by reasoning): nothing usable."""
    if text is None:
        return None
    out = _THINK.sub("", text)
    if re.search(r"<think>", out, re.IGNORECASE):
        return None
    out = re.sub(r"</think>", "", out, flags=re.IGNORECASE)  # a stray closing tag
    return out.strip() or None


# ---- Timbre v3.0 voice tags (the LLM chooses them; only the allowed gentle ones survive) ---------------------
_TAG = re.compile(r"<\s*([a-z][a-z ]{1,20})\s*>", re.IGNORECASE)


def split_voice_tags(text: str, allowed: tuple[str, ...] = config.VOICE_TAGS, max_tags: int = 2) -> tuple[str, str]:
    """(clean text for the screen and the boundary checks, text for TTS with at most `max_tags` allowed tags).

    Tags are case-sensitive for Timbre, so they are normalised to the exact allowed spelling; anything else in
    angle brackets is removed from both."""
    ok = {t[1:-1].lower(): t for t in allowed}
    kept = 0

    def spoken(mt: re.Match[str]) -> str:
        nonlocal kept
        tag = ok.get(mt.group(1).strip().lower())
        if tag and kept < max_tags:
            kept += 1
            return tag + " "
        return ""

    clean = re.sub(r"\s{2,}", " ", _TAG.sub("", text)).strip()
    voice = re.sub(r"\s{2,}", " ", _TAG.sub(spoken, text)).strip()
    return clean, voice


UNDERSTAND_INTENTS = (
    "chat", "reminder_add", "reminder_done", "medicine_taken", "medicine_query", "media", "news", "video_call",
    "call_family", "message_family", "today_query", "undo", "stop", "health_complaint", "unclear",
)
_OLD_TO_NEW = {
    "CHAT": "chat", "CREATE_REMINDER": "reminder_add", "COMPLETE_REMINDER": "reminder_done",
    "MED_TAKEN": "medicine_taken", "MED_SNOOZE": "medicine_taken", "MEDICAL_QUESTION": "medicine_query",
    "OPEN_MEDIA": "media", "OPEN_LINK": "media", "OPEN_WHATSAPP": "message_family",
    "NEWS_READ": "news", "CALL_FAMILY_REMINDER": "call_family", "REQUEST_CAREGIVER": "message_family",
    "LIST_TODAY": "today_query", "GET_APPOINTMENT": "today_query", "CONFIRM_NO": "undo",
    "DECLINE_TOPIC": "stop", "MEDIA_CONTROL": "stop", "TIME_QUERY": "today_query",
    "NEXT_UP": "today_query", "UNKNOWN": "unclear", "DISTRESS": "health_complaint",
    "SYMPTOM": "health_complaint",
}


def _conversation_rules(language: str) -> str:
    lang_name, script = _LANG_NAMES.get(language, _LANG_NAMES["mr"])
    return (
        f"You are Arjun, a warm, practical male voice companion for an elderly speaker. "
        f"Always answer in {lang_name}, written in {script} script, the way a kind younger man in her family "
        f"would speak. Speak as a man: use masculine forms for yourself (सांगतो, विचारतो, करतो, ऐकतो, बघतो; "
        f"never सांगते / विचारते / करते). Address her with respectful तुम्ही / तुमचं, never तू. "
        f"Her words come from speech-to-text and may be noisy, cut off or misspelled; infer the most likely "
        f"meaning from the whole sentence and the conversation, and answer the meaning, not the noise. "
        f"NEVER ACT DUMB. ALWAYS TRY TO GIVE A SOLUTION: if she asks how to do something, give the practical "
        f"steps; if she asks about her day, reminders, family or an app, give the useful answer or the next step. "
        f"If she asks a real question (a festival, a word's meaning, how a household or garden thing works, general "
        f"knowledge) ANSWER IT properly in 1-3 simple sentences; never say 'I don't know', 'I cannot' or 'teach me' "
        f"when you can answer. For a recipe, give 2-3 simple steps in 2-3 short sentences, then finish with the exact offer "
        f"'व्हिडिओ लावू?'. "
        f"Never give medical/health/medicine advice, doses or diagnosis. Never state news facts from memory; news "
        f"may come only from the approved news source. "
        f"USE WHAT YOU KNOW about her: call the people she told you about by name and relation (नातू आर्यन), recall "
        f"what she said earlier today ('सकाळी तुम्ही सांगितलं होतं की…'), and follow up on an event she mentioned "
        f"('कालचा डॉक्टरचा दिवस कसा गेला?') when the facts below say it happened; never invent a name, event or "
        f"memory that is not in the conversation or the facts. Keep the conversation in mind: when she says 'तो', "
        f"'त्याचं', 'ते', or 'मी काय म्हणाले', find what it refers to in what was said before. "
        f"When she asks what you remember, what she likes or what she told you, answer ONLY from this conversation and "
        f"the facts below; if it is not there, say plainly that you do not remember and invite her to tell you; "
        f"never guess a preference, a name or an event. "
        f"Write AT MOST ONE question in a reply, and many replies should have none: sometimes just respond warmly "
        f"to what she said. Never repeat a question that was already asked today. "
        f"Reply in 1-2 short sentences; a how-to or an explanation may use up to 3 short sentences. Never write a "
        f"list or a long explanation. "
        f"Never give medical advice or a diagnosis, and never suggest a dose, rest, water or a doctor visit on your "
        f"own. If she says she plans to rest, brief agreement is allowed (for example, 'हो, आराम करा, नंतर बोलूया.'); "
        f"do not add any other advice. If she mentions another health problem, acknowledge it and ask what she needs, "
        f"or point her to her family. "
        f"Never claim to be human or to have a body, feelings, a family or experiences. If she asks whether you "
        f"are a human or a machine, say clearly that you are an AI companion. "
        f"Never say you missed her, never make her feel guilty, and encourage her to talk to her family. "
        f"Never invent facts about people or places she mentions. Do not end every reply with a generic "
        f"how-are-you-feeling question, and never answer an actionable request by saying you cannot do it. "
        f"Answer her latest sentence first; never change the subject or contradict something she said earlier today. "
        f"If uncertain, make one specific clarification naming your best guess, and do not repeat that question within 10 minutes. "
        f"Examples: 'आज वांग्याचं भरीत केलं' → 'वांग्याचं भरीत छान झालं असेल; तुम्ही ते कशाबरोबर खाल्लं?' "
        f"'राहुल जेवला असेल का?' → 'कदाचित जेवला असेल; तुम्हाला त्याची काळजी वाटतेय.' "
        f"'भूक लागली आहे' → 'तुम्हाला भूक लागली आहे; घरात खायला काय आहे?' "
        f"'मला काल पुण्याला जायचं होतं' → 'पुण्याला जाणं झालं का?' "
        f"'हे बटण कसं दाबू?' → 'बटणावर एकदा हलकेच दाबा; स्क्रीनवर काय दिसतंय?' "
        f"'माझा मुलगा उद्या येणार आहे' → 'छान, उद्या तुमचा मुलगा भेटायला येणार आहे.' "
    )


def _system_prompt(
    language: str,
    now: datetime | None,
    interests: list[str] | None,
    context: str,
    *,
    voice_tags: bool,
    json_contract: bool,
    memory: str = "",
) -> str:
    system = _conversation_rules(language)
    if now is not None:
        system += (
            f"The current local time is {now:%H:%M} on {now:%A}, {now.date().isoformat()}; mention it only if "
            f"she asks about the time or day. "
        )
    if interests:
        system += (
            f"Things she enjoys talking about: {', '.join(interests[:4])}. You may ask her to tell you about "
            f"one of these. "
        )
    if context:
        system += (
            "USER CONTEXT (from the family dashboard and today's records; use it only when it helps the reply, "
            "never read it out as a list, never mention that you have a dashboard):\n" + context + "\n"
        )
        system += (
            "Address her using the exact 'address her as' value in USER CONTEXT. Never invent a form of address; "
            "in particular, never call her ताई unless that exact value is ताई. "
        )
    if memory:
        system += memory + "\n"
    if voice_tags:
        system += (
            "Your reply is spoken aloud. When it truly fits, you may put ONE voice tag right before the words "
            f"it should colour, chosen from exactly: {' '.join(config.VOICE_TAGS)}. Most replies need no tag. "
            "Never invent another tag. "
        )
    if json_contract:
        system += (
            "Return ONLY one JSON object, no prose and no markdown:\n"
            '{"intent": one of ' + json.dumps(list(UNDERSTAND_INTENTS)) + ', '
            '"slots": {"task": string|null, "date": "YYYY-MM-DD"|null, "time": "HH:MM"|null, '
            '"time_ambiguous": true|false, "query": string|null, "media_kind": '
            '"news|recipe|music|devotional|exercise|video|unknown"|null, "media_specific": true|false, '
            '"control": "stop|pause|resume|next|volume_up|volume_down"|null, "contact": string|null, '
            '"confirm": "yes"|"no"|null, "choice": integer|string|null, "checkin_answer": '
            '"done|skipped"|null, "bp": {"systolic": integer, "diastolic": integer}|null}, '
            '"reply": string, "confidence": number 0-1}\n'
            "Intent meanings: chat = ordinary talk or a question you can answer; video_call = start a live video call with a family contact, including direct commands like 'Rahul la call kar'; reminder_add = set a reminder; "
            "reminder_done = she finished a task/reminder; medicine_taken = she says she took her medicine; "
            "medicine_query = a question or worry about medicines/doses/side effects; media = play/open music, "
            "bhajan, a video, a recipe, a family link or WhatsApp; news = read or play news; call_family = she "
            "wants to talk about calling or remember to call family; a direct command to call a named contact is video_call; message_family = send a message or ask family for help; "
            "today_query = ask what is on today/tomorrow, the time, the date or the next appointment; undo = "
            "cancel or undo what was just done; stop = stop the current media/topic; health_complaint = she "
            "reports a symptom or feeling unwell; unclear = you truly cannot tell. "
            "For chat, write the full reply in `reply`. For an action intent, put the details in `slots` and keep "
            "`reply` short; the app reads the action back exactly. Never put a URL in any slot. Resolve relative "
            "dates/times from the clock above; if AM/PM is unclear set time_ambiguous=true and time=null. "
            "Never invent a task, date or time that was not said. A medicine question is NEVER answered here: "
            "intent=medicine_query. If the utterance is a story or background talk that merely mentions a "
            "medicine, media or family, it is chat, not an action."
        )
    return system


def _parse_json_object(raw: str | None) -> dict[str, Any] | None:
    """The first JSON object in a model reply; tolerates code fences and stray prose."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except (ValueError, TypeError):
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start:end + 1])
            return data if isinstance(data, dict) else None
        except (ValueError, TypeError):
            return None


def trim_to_sentence(text: str) -> str:
    """Cut a reply that ran into max_tokens back to its last full sentence (never mid-word)."""
    out = text.strip()
    if not out:
        return out
    if out[-1] in ".!?।…":
        return out
    cut = max(out.rfind("."), out.rfind("!"), out.rfind("?"), out.rfind("।"), out.rfind("…"))
    if cut >= 0:
        return out[: cut + 1].strip()
    return out


LIFE_FACT_KINDS = ("person", "like", "dislike", "routine", "place", "event", "concern")


class LlmBusy(httpx.TransportError):
    """Not sent: over the concurrency / per-minute limit, or the provider said 429 recently. Rules answer."""


class Limiter:
    """Concurrency (at most N calls in flight) + rate (at most M per minute) + backoff after a provider 429.

    Waits at most two seconds for an in-flight call, then reports busy to the turn fallback."""

    def __init__(self, max_concurrent: int = 4, per_minute: int = 60, clock: Any = time.monotonic) -> None:
        import threading

        self._sem = threading.BoundedSemaphore(max(1, max_concurrent))
        self.per_minute, self.clock = per_minute, clock
        self._calls: list[float] = []
        self._cool_until = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        now = self.clock()
        with self._lock:
            self._calls = [t for t in self._calls if now - t < 60.0]
            cooldown_wait = max(0.0, self._cool_until - now)
            rate_wait = max(0.0, 60.0 - (now - self._calls[0])) if len(self._calls) >= self.per_minute else 0.0
            wait_s = min(2.0, max(cooldown_wait, rate_wait))
        if wait_s:
            time.sleep(wait_s)
        now = self.clock()
        with self._lock:
            self._calls = [t for t in self._calls if now - t < 60.0]
            if now < self._cool_until:
                raise LlmBusy("provider asked us to slow down")
            if len(self._calls) >= self.per_minute:
                raise LlmBusy("per-minute LLM limit reached")
            self._calls.append(now)
        if not self._sem.acquire(timeout=2.0):
            with self._lock:
                for index in range(len(self._calls) - 1, -1, -1):
                    if self._calls[index] == now:
                        del self._calls[index]
                        break
            raise LlmBusy("LLM queue wait exceeded")

    def release(self) -> None:
        self._sem.release()

    def cool_down(self, seconds: float) -> None:
        with self._lock:
            self._cool_until = max(self._cool_until, self.clock() + seconds)


MOODS = ("happy", "calm", "neutral", "lonely", "sad", "worried", "unwell", "distressed")
LEVELS = ("normal", "watch", "urgent", "emergency")


def load_intent_schema() -> dict[str, Any]:
    return json.loads((Path(config.SCHEMA_DIR) / "intent.json").read_text(encoding="utf-8"))


class EvonClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        http: httpx.Client | None = None,
        schema: dict[str, Any] | None = None,
        api_key: str = "",
        send_template_kwargs: bool = True,
        provider: str = "evon",
        max_tokens: int = 250,  # LLM_MAX_TOKENS default; 80 cut replies mid-sentence
        timeout_s: float = 4.0,
        reasoning_off: bool = False,
        limiter: Limiter | None = None,
        voice_tags: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.provider = provider
        self.max_tokens = max_tokens
        self.usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}  # running totals for this client
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.http = http or httpx.Client(timeout=timeout_s, headers=headers)
        self.schema = schema or load_intent_schema()
        self.send_template_kwargs = send_template_kwargs
        self.reasoning_off = reasoning_off
        self.limiter = limiter or Limiter()
        self.voice_tags = voice_tags

    def _chat(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        purpose: str = "chat",
        timeout: float | None = None,
        meta: dict[str, Any] | None = None,
        **extra: Any,
    ) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            **extra,
        }
        if self.send_template_kwargs:
            # reasoning traces add latency in the live voice path
            body["chat_template_kwargs"] = {"enable_thinking": False}
        if self.reasoning_off:
            body["reasoning_effort"] = None  # Sarvam: answer directly, no hidden thinking tokens
        debug_log(
            "llm_request", purpose=purpose, provider=self.provider, model=self.model,
            messages=messages, system_chars=len(messages[0]["content"]) if messages else 0,
            history_count=max(0, len(messages) - 2), max_tokens=body.get("max_tokens"),
            temperature=temperature,
        )
        t0 = time.perf_counter()
        record: dict[str, Any] = {
            "provider": self.provider,
            "model": self.model,
            "purpose": purpose,
        }
        try:
            self.limiter.acquire()
        except LlmBusy as exc:
            record.update(ok=False, error="LlmBusy", detail=str(exc))
            log.info(json.dumps(record))
            raise
        try:
            r = self.http.post(
                f"{self.base_url}/chat/completions",
                json=body,
                **({"timeout": timeout} if timeout is not None else {}),
            )
            if r.status_code == 429:  # back off; the rules answer until then
                try:
                    wait = float(r.headers.get("retry-after", "30"))
                except ValueError:
                    wait = 30.0
                self.limiter.cool_down(min(max(wait, 1.0), 300.0))
            r.raise_for_status()
            data = r.json()
            finish = data["choices"][0].get("finish_reason")  # "length" = the reply was cut by max_tokens
            content = strip_thinking(data["choices"][0]["message"].get("content"))
            if content is None:
                raise ValueError("no visible answer (only reasoning, or empty)")
        except Exception as exc:
            # one line per call, never the transcript or the reply: provider, model, latency, tokens
            record.update(
                ok=False,
                error=type(exc).__name__,
                latency_ms=round((time.perf_counter() - t0) * 1000),
            )
            log.info(json.dumps(record))
            raise
        finally:
            self.limiter.release()
        usage = data.get("usage") or {}
        if meta is not None:
            meta["finish_reason"] = finish
        self.usage["calls"] += 1
        self.usage["prompt_tokens"] += usage.get("prompt_tokens") or 0
        self.usage["completion_tokens"] += usage.get("completion_tokens") or 0
        record.update(
            ok=True,
            latency_ms=round((time.perf_counter() - t0) * 1000),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            finish_reason=finish,
        )
        log.info(json.dumps(record))
        debug_log(
            "llm_reply", purpose=purpose, raw=content, finish_reason=finish,
            latency_ms=record["latency_ms"], prompt_tokens=record["prompt_tokens"],
            completion_tokens=record["completion_tokens"],
        )
        return content

    def extract_intent(
        self,
        text: str,
        language: str,
        now: datetime,
        wake: str,
        lunch: str,
        dinner: str,
        timeout: float | None = None,
    ) -> dict[str, Any] | None:
        lang_name, script = _LANG_NAMES.get(language, _LANG_NAMES["mr"])
        system = (
            f"You are the intent extractor for Arjun, a voice care companion. The user speaks "
            f"{lang_name} ({script} or romanised). Output ONLY one JSON object matching this "
            f"schema, nothing else: {json.dumps(self.schema)}. "
            f"Today is {now.date().isoformat()}, the current local time is {now:%H:%M}. "
            f"User wake time {wake}, lunch {lunch}, dinner "
            f"{dinner}. Resolve relative dates/times from these. If AM/PM is unclear set "
            f"time_ambiguous=true and time=null. Never invent a task, date or time that was not "
            f"said. Do not give medical advice. For app requests (songs / YouTube, news, WhatsApp, a saved family "
            f"link, stop / next / volume) use OPEN_MEDIA, NEWS_READ, OPEN_WHATSAPP, OPEN_LINK or MEDIA_CONTROL: put "
            f"only the song or singer words in media_query, the spoken name of a link or person in link_label, and "
            f"the control word in media_control. Never output a URL."
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": text}]
        for _ in range(2):  # initial try + one retry
            try:
                raw = self._chat(
                    messages,
                    config.EXTRACTION_TEMPERATURE,
                    purpose="intent",
                    timeout=timeout,
                    max_tokens=250,
                    response_format={"type": "json_object"},
                )
                data = json.loads(raw)
                jsonschema.validate(data, self.schema)
                return data  # type: ignore[no-any-return]
            except (httpx.HTTPError, ValueError, KeyError, jsonschema.ValidationError):
                continue
        return None

    def media_understanding(self, text: str, timeout: float | None = None) -> dict[str, Any] | None:
        """One strict-JSON reading of a media request: {kind, topic, specific}. One attempt, no retry.

        Deliberately separate from extract_intent: the intent schema is about reminders and care, and a media
        request must not be forced through it. No URL, id or reply may come out of here (turn.py validates).
        """
        system = (
            "You classify ONE media request for Arjun, a voice companion for an older Marathi speaker. "
            'Output ONLY one JSON object: {"kind": "news|recipe|music|devotional|exercise|video|unknown", '
            '"topic": "<what to search for, in Marathi, 1-6 words; empty if nothing>", '
            '"specific": true|false}. '
            "kind: news = news/headlines/live news; recipe = how to cook or make a dish; music = songs; "
            "devotional = bhajan/abhang/aarti/kirtan; exercise = exercise/yoga; video = another video; "
            "unknown = she did not say what to watch or listen to. "
            "specific=true only when she named a particular singer, song, dish, programme or channel; "
            "a category (songs, bhajans, news, sweets, exercise) is false. Never output a URL. No prose."
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": text}]
        try:
            raw = self._chat(
                messages,
                0.0,
                purpose="media",
                timeout=timeout,
                max_tokens=120,
                response_format={"type": "json_object"},
            )
            data = json.loads(raw)
        except (httpx.HTTPError, ValueError, KeyError):
            return None
        return data if isinstance(data, dict) else None

    def safety_check(self, text: str, timeout: float | None = None) -> dict[str, Any] | None:
        """Second safety layer: strict JSON {emergency: bool, distress: bool} for ONE utterance. One attempt, no retry.

        It only classifies. It never writes a reply and never gives advice. None = unusable (timeout, rate limit,
        bad JSON), and the caller then applies its fail-safe words."""
        system = (
            "You are a safety classifier for Arjun, a voice companion for an older Marathi speaker. Speech-to-text "
            "may be noisy and English words are often written in Devanagari (हार्ट अटॅक = heart attack). "
            'Output ONLY one JSON object: {"emergency": true|false, "distress": true|false}. '
            "emergency = she says she is having, right now, a heart attack, chest pain, trouble breathing, a stroke, "
            "fainting, a fall, heavy bleeding or a dangerously high BP or low sugar. A story about the past, a film, "
            "a question about someone else's past, or a figure of speech is false. "
            "distress = she says she wants to die, is being hurt or is very afraid. No prose, no advice."
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": text}]
        try:
            raw = self._chat(
                messages, 0.0, purpose="safety", timeout=timeout, max_tokens=40,
                response_format={"type": "json_object"},
            )
            data = json.loads(raw)
        except (httpx.HTTPError, ValueError, KeyError):
            return None
        return data if isinstance(data, dict) else None

    def checkin_understanding(self, topic: str, text: str, timeout: float | None = None) -> dict[str, Any] | None:
        """One strict-JSON reading of her answer to ONE check-in question: {topic, status, note}. One attempt.

        Only status matters (done | not_done | unclear). `note` is ignored by the caller and never stored or shown:
        what she said is never kept. Used only when the word rules could not tell."""
        system = (
            "You read ONE short answer from an older Marathi speaker to a daily check-in question from Arjun, "
            f"a voice companion. The question was about: {topic}. "
            'Output ONLY one JSON object: {"topic": "<the same topic>", "status": "done|not_done|unclear", '
            '"note": "<at most 6 words, in English>"}. '
            "done = she says it happened (or yes / remembers); not_done = she says it did not (or no); "
            "unclear = anything else, a different subject, or she is asking something. Never give advice. No prose."
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": text}]
        try:
            raw = self._chat(
                messages, 0.0, purpose="checkin", timeout=timeout, max_tokens=80,
                response_format={"type": "json_object"},
            )
            data = json.loads(raw)
        except (httpx.HTTPError, ValueError, KeyError):
            return None
        return data if isinstance(data, dict) else None

    def understand_turn(
        self,
        text: str,
        language: str,
        now: datetime,
        history: list[tuple[str, str]] | None = None,
        context: str = "",
        interests: list[str] | None = None,
        timeout: float | None = None,
        memory: str = "",
    ) -> dict[str, Any] | None:
        """ONE call for a non-safety turn: strict JSON {intent, slots, reply, confidence}.

        The whole sentence, this conversation's history and the family/dashboard context go in together, so the
        model reads meaning rather than keywords. Returns None when the provider is down, times out or returns
        unusable JSON (the caller then uses the rule parser). A provider that ignores the JSON contract and
        answers in plain prose is accepted as a chat reply (legacy/fake providers); an old intent-only JSON
        shape is accepted too, marked `legacy`, and the caller may fetch a companion reply once.
        """
        system = _system_prompt(
            language, now, interests, context, voice_tags=self.voice_tags, json_contract=True, memory=memory
        )
        messages = [{"role": "system", "content": system}]
        messages += [{"role": role, "content": content} for role, content in (history or [])]
        messages.append({"role": "user", "content": "This is a speech transcript and may contain recognition errors; infer the most likely meaning. Raw transcript: " + text})
        meta: dict[str, Any] = {}
        try:
            raw = self._chat(
                messages,
                config.COMPANION_TEMPERATURE,
                purpose="understand",
                timeout=timeout,
                meta=meta,
                top_p=config.COMPANION_TOP_P,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
            )
        except (ValueError, KeyError):
            return None
        # httpx errors are deliberately NOT swallowed here: the caller logs the real reason (timeout vs provider).
        data = _parse_json_object(raw)
        if data is None:
            # A provider that answered in plain prose: that prose is the reply. No second call.
            prose = strip_thinking(raw)
            if not prose or "{" in prose:
                return None
            return {
                "intent": "chat", "slots": {}, "reply": prose, "confidence": 0.55,
                "legacy": False, "legacy_reply": True, "finish_reason": meta.get("finish_reason"),
            }
        intent_raw = data.get("intent")
        if not isinstance(intent_raw, str):
            return None
        legacy = False
        if intent_raw in UNDERSTAND_INTENTS:
            intent = intent_raw
            slots = data.get("slots") if isinstance(data.get("slots"), dict) else {}
        elif intent_raw in _OLD_TO_NEW:
            legacy = True
            intent = _OLD_TO_NEW[intent_raw]
            slots = {
                "task": data.get("task"), "date": data.get("date"), "time": data.get("time"),
                "time_ambiguous": bool(data.get("time_ambiguous")),
                "query": data.get("media_query") or data.get("link_label"),
                "control": data.get("media_control"),
            }
        else:
            return {
                "intent": intent_raw, "slots": {}, "reply": "", "confidence": 0.0,
                "legacy": False, "legacy_intent": "", "legacy_reply": False,
                "finish_reason": meta.get("finish_reason"), "bad_intent": True,
            }
        try:
            confidence = float(data.get("confidence", 0.6))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = min(1.0, max(0.0, confidence))
        reply = str(data.get("reply") or "").strip()
        if meta.get("finish_reason") == "length" and reply:
            reply = trim_to_sentence(reply)
        return {
            "intent": intent,
            "slots": slots,
            "reply": reply,
            "confidence": confidence,
            "legacy": legacy,
            "legacy_intent": intent_raw if legacy else "",
            "legacy_reply": False,
            "finish_reason": meta.get("finish_reason"),
        }

    def companion_reply(
        self,
        text: str,
        language: str,
        now: datetime | None = None,
        history: list[tuple[str, str]] | None = None,
        interests: list[str] | None = None,
        timeout: float | None = None,
        correction: str = "",
        context: str = "",
        memory: str = "",
    ) -> str | None:
        """`history` is this conversation's earlier (role, text) turns, oldest first. `context` (who she is, what she
        told Arjun) and `memory` (the session summary, the open question) go in exactly as for understand_turn."""
        system = _system_prompt(
            language, now, interests, context, voice_tags=self.voice_tags, json_contract=False, memory=memory
        )
        if correction:
            system += (
                "Your previous reply was rejected by the safety check (" + correction + "). Write a different "
                "reply that keeps the same meaning, is 1-2 short sentences, gives a practical next step, and "
                "breaks none of the rules above. Never mention the check. "
            )
        messages = [{"role": "system", "content": system}]
        messages += [{"role": role, "content": content} for role, content in (history or [])]
        messages.append({"role": "user", "content": "This is a speech transcript and may contain recognition errors; infer the most likely meaning. Raw transcript: " + text})
        meta: dict[str, Any] = {}
        try:
            out = self._chat(
                messages,
                config.COMPANION_TEMPERATURE,
                purpose="companion",
                timeout=timeout,
                meta=meta,
                top_p=config.COMPANION_TOP_P,
                max_tokens=self.max_tokens,
            )
        except (httpx.HTTPError, ValueError, KeyError):
            return None
        if meta.get("finish_reason") == "length":
            out = trim_to_sentence(out)
        return out.strip() or None

    def simplify_reply(self, reply: str, language: str, timeout: float | None = None) -> str | None:
        """Simplify only Arjun's prior reply. The caller validates all numeric/time tokens and falls back exactly."""
        lang_name, script = _LANG_NAMES.get(language, _LANG_NAMES["mr"])
        system = (
            f"Rewrite the supplied Arjun reply in simpler, shorter spoken {lang_name} ({script}) for an older listener. "
            "Preserve exactly the same meaning and every fact. Do not add advice, a question, or a greeting. "
            "Keep all digits, decimal values, and HH:MM time strings exactly unchanged. Use short familiar words. "
            "Return only the rewritten reply."
        )
        try:
            value = self._chat(
                [{"role": "system", "content": system}, {"role": "user", "content": reply}],
                config.COMPANION_TEMPERATURE, purpose="companion", timeout=timeout, max_tokens=160,
                top_p=config.COMPANION_TOP_P,
            )
            return value.strip() or None
        except (httpx.HTTPError, ValueError, KeyError):
            return None


    def summarize_conversation(
        self, turns: list[tuple[str, str]], language: str, timeout: float | None = 10.0
    ) -> dict[str, Any] | None:
        """For the family dashboard: {"summary", "mood", "severity", "topics"}. None on any failure.

        Runs after the conversation ended (never in the voice path). The summary is a short paraphrase in the
        requested language:
        no quotes, no medical judgement, nothing invented. The caller keeps a rules floor for severity."""
        if not turns:
            return None
        lines = "\n".join(f"{'Elder' if who == 'user' else 'Arjun'}: {said}" for who, said in turns[-40:])
        system = (
            "You write a short note for the family of an elderly person about one conversation she had with "
            "Arjun, an AI voice companion. Output ONLY one JSON object: "
            '{"summary": string (in ' + json.dumps(_LANG_NAMES.get(language, _LANG_NAMES["en"])[0]) + ', exactly 2-3 brief lines, what she talked about and how she seemed; '
            "paraphrase, no quotation marks, never quote her or provide a transcript; report only what she said, "
            "never diagnose, never guess causes, never "
            'give advice), "mood": one of ' + json.dumps(list(MOODS)) + ', "severity": one of '
            + json.dumps(list(LEVELS)) + ' (normal = ordinary chat; watch = lonely, sad, worried, a complaint '
            "worth a call today; urgent = asked for help, very upset, pain; emergency = chest pain, a fall, "
            'cannot breathe, bleeding), "topics": up to 4 short English words}.'
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": lines}]
        for _ in range(2):
            try:
                raw = self._chat(messages, config.EXTRACTION_TEMPERATURE, purpose="summary", timeout=timeout,
                                 max_tokens=220, response_format={"type": "json_object"})
                data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
                if data.get("mood") not in MOODS or data.get("severity") not in LEVELS:
                    raise ValueError("bad enum")
                summary = str(data.get("summary") or "").strip()[:400]
                lines = [line.strip() for line in summary.splitlines() if line.strip()]
                if not 2 <= len(lines) <= 3 or any(q in summary for q in ('"', "'", "“", "”", "‘", "’")):
                    raise ValueError("summary must have 2-3 unquoted lines")
                topics = [str(t)[:30] for t in (data.get("topics") or [])][:4]
                return {"summary": summary, "mood": data["mood"], "severity": data["severity"], "topics": topics}
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                continue
        return None


    def extract_life_facts(
        self, turns: list[tuple[str, str]], language: str, known: list[str] | None = None, timeout: float | None = 12.0
    ) -> list[dict[str, Any]] | None:
        """After a conversation: the durable facts about HER life, as strict JSON
        {"facts": [{"kind", "fact", "confidence"}]}. None on any failure. Runs after the conversation, never in the
        voice path. The caller (core-api) still validates every fact: this only PROPOSES (boundary 1).

        Only what she said; nothing guessed; no numbers, addresses, money, medicines or diagnoses; a body complaint
        only as a plainly worded concern. People are written "name — relation" so that the same person is one fact."""
        if not turns:
            return None
        lines = "\n".join(f"{'Elder' if who == 'user' else 'Arjun'}: {said}" for who, said in turns[-40:])
        system = (
            "From this conversation between an elderly Marathi woman and Arjun (an AI companion), list the DURABLE "
            "facts about HER life that Arjun should remember on later days. Output ONLY one JSON object: "
            '{"facts": [{"kind": one of ["person","like","dislike","routine","place","event","concern"], '
            '"fact": string, "confidence": number 0-1}]}. '
            "Write each fact in short natural Marathi (Devanagari), at most 12 words, in her own words. "
            "person = someone she names: write 'नाव — नातं' (for example 'आर्यन — नातू', 'सुमन — शेजारीण'). "
            "like/dislike = something she enjoys or avoids; routine = something she does regularly; place = a place "
            "that matters to her; event = something she says will happen or happened (a visit, a trip, a function), "
            "worded with the day word she used (उद्या, काल, शुक्रवारी); concern = a worry or a body complaint worded "
            "plainly as she said it ('गुडघा दुखतो असं सांगितलं'), never a diagnosis. "
            "RULES: only what SHE said, never what Arjun said; nothing guessed; skip greetings and small talk; "
            "NEVER include any number or digit, phone number, address, money, medicine, tablet, dose or disease name; "
            "at most 6 facts; do not repeat a fact that is already known. Return {\"facts\": []} when there is nothing."
        )
        if known:
            system += " ALREADY KNOWN: " + " | ".join(known[:30])
        messages = [{"role": "system", "content": system}, {"role": "user", "content": lines}]
        for _ in range(2):
            try:
                raw = self._chat(messages, config.EXTRACTION_TEMPERATURE, purpose="facts", timeout=timeout,
                                 max_tokens=500, response_format={"type": "json_object"})
                data = _parse_json_object(raw)
                items = data.get("facts") if data else None
                if not isinstance(items, list):
                    raise ValueError("no facts list")
                out: list[dict[str, Any]] = []
                for item in items[:6]:
                    if not isinstance(item, dict):
                        continue
                    kind, fact = str(item.get("kind") or ""), str(item.get("fact") or "").strip()
                    if kind not in LIFE_FACT_KINDS or not 2 <= len(fact) <= 140:
                        continue
                    try:
                        conf = min(1.0, max(0.0, float(item.get("confidence", 0.7))))
                    except (TypeError, ValueError):
                        conf = 0.7
                    out.append({"kind": kind, "fact": fact, "confidence": conf})
                return out
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                continue
        return None
