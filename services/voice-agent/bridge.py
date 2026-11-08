"""HTTP bridge from the voice worker to reasoning. No business logic lives in the voice agent.

Rule: a failed or slow reasoning call must never leave Aaji in silence. `reply_or_fallback`
always returns something speakable; the error is logged, never spoken in detail.
"""

import logging
import os
import time
from dataclasses import dataclass

import httpx
from safety_words import is_distress, is_emergency

REASONING_URL = os.environ.get("REASONING_URL", "http://127.0.0.1:8001")
# A voice user cannot wait long: fail fast and speak the fallback instead.
REASONING_TIMEOUT_S = float(os.environ.get("REASONING_TIMEOUT_S", "7.5"))

log = logging.getLogger("arjun.bridge")

_client: httpx.Client | None = None


def _shared_client() -> httpx.Client:
    """One pooled client for the worker process (thread-safe for concurrent requests)."""
    global _client
    if _client is None:
        _client = httpx.Client(timeout=REASONING_TIMEOUT_S)
    return _client


@dataclass
class BridgeReply:
    text: str
    mode: str
    awaiting_confirmation: bool
    round_trip_ms: float
    screen: str = "reply"  # reply | story | confirm | saved | safety (decided by reasoning)
    intent: str = ""
    speech: str = ""  # what to say, may carry Timbre v3 tags; empty = say `text`
    source: str = ""  # rules | llm: who wrote the answer (for the turn log)
    action: dict | None = None  # type: ignore[type-arg]  # what the elder screen opens / does: {type, kind, value, title}
    speech_style: dict | None = None  # type: ignore[type-arg]
    silent: bool = False
    language: str = ""


def ask_reasoning(
    user_id: int, transcript: str, http: httpx.Client | None = None, language: str | None = None,
) -> BridgeReply:
    """Call reasoning /turn. Raises on HTTP or network errors (see reply_or_fallback)."""
    client = http or _shared_client()
    t0 = time.perf_counter()
    payload = {"user_id": user_id, "text": transcript}
    if language:
        payload["language_code"] = language
    r = client.post(f"{REASONING_URL}/turn", json=payload)
    r.raise_for_status()
    data = r.json()
    return BridgeReply(
        text=data["reply"],
        mode=data["mode"],
        awaiting_confirmation=data["awaiting_confirmation"],
        round_trip_ms=(time.perf_counter() - t0) * 1000,
        screen=data.get("screen", "reply"),
        intent=data.get("intent", ""),
        speech=data.get("speech", "") or "",
        source=data.get("source", "") or "",
        action=data.get("action") or None,
        speech_style=data.get("speech_style") or None,
        silent=bool(data.get("silent", False)),
        language=str(data.get("language") or language or ""),
    )


def fallback_text(language: str, transcript: str = "") -> str:
    """A local, topic-naming repair used only when reasoning is unreachable; never a generic repeat line."""
    prefix = (language or "mr").replace("_", "-").split("-", 1)[0].lower()
    text = " ".join((transcript or "").split())
    if not text:
        return ""
    if is_emergency(text):
        return {
            "mr": "तुम्हाला आत्ता तातडीची मदत हवी आहे का? जवळच्या घरच्यांना बोलवूया?",
            "hi": "क्या आपको अभी तुरंत मदद चाहिए? पास में किसी अपने को बुलाएँ?",
            "en": "Do you need urgent help now? Should someone nearby come to you?",
            "ta": "உங்களுக்கு இப்போது அவசர உதவி வேண்டுமா? அருகில் உள்ள குடும்பத்தினரை அழைக்கவா?",
            "kn": "ನಿಮಗೆ ಈಗ ತುರ್ತು ಸಹಾಯ ಬೇಕೇ? ಹತ್ತಿರದ ಕುಟುಂಬದವರನ್ನು ಕರೆಯಬೇಕೇ?",
            "bn": "আপনার কি এখন জরুরি সাহায্য দরকার? কাছের পরিবারের কাউকে ডাকব?",
            "gu": "શું તમને અત્યારે તાત્કાલિક મદદ જોઈએ છે? નજીકના પરિવારજનોને બોલાવું?",
            "pa": "ਕੀ ਤੁਹਾਨੂੰ ਹੁਣੇ ਫੌਰੀ ਮਦਦ ਚਾਹੀਦੀ ਹੈ? ਨੇੜੇ ਦੇ ਪਰਿਵਾਰਕ ਜੀਅ ਨੂੰ ਬੁਲਾਵਾਂ?",
            "te": "మీకు ఇప్పుడు అత్యవసర సహాయం కావాలా? దగ్గరలోని కుటుంబ సభ్యులను పిలవనా?",
            "ml": "ഇപ്പോൾ അടിയന്തര സഹായം വേണോ? അടുത്തുള്ള വീട്ടുകാരെ വിളിക്കട്ടേ?",
            "or": "ଆପଣଙ୍କୁ ଏବେ ଜରୁରୀ ସାହାଯ୍ୟ ଦରକାର କି? ପାଖରେ ଥିବା ପରିବାର ଲୋକଙ୍କୁ ଡାକିବି?",
        }.get(prefix, "तुम्हाला आत्ता तातडीची मदत हवी आहे का? जवळच्या घरच्यांना बोलवूया?")
    if is_distress(text):
        return {
            "mr": "तुम्हाला खूप त्रास होतोय असं वाटतंय. आत्ता घरच्यांपैकी कोणाशी बोलायचं आहे?",
            "hi": "आप बहुत परेशान लग रहे हैं। क्या आप अभी अपने परिवार में किसी से बात करना चाहेंगे?",
            "en": "It sounds like you are in a lot of pain. Would you like to talk to someone in your family now?",
            "ta": "உங்களுக்கு மிகவும் கஷ்டமாக இருக்கிறது போல. இப்போது குடும்பத்தில் யாரிடமாவது பேச விரும்புகிறீர்களா?",
            "kn": "ನಿಮಗೆ ತುಂಬಾ ಕಷ್ಟವಾಗುತ್ತಿದೆ ಅನಿಸುತ್ತದೆ. ಈಗ ಮನೆಯವರಲ್ಲಿ ಯಾರೊಂದಿಗಾದರೂ ಮಾತನಾಡಬೇಕೇ?",
            "bn": "আপনার খুব কষ্ট হচ্ছে মনে হচ্ছে। এখন পরিবারের কারও সঙ্গে কথা বলতে চান?",
            "gu": "તમને ઘણું મુશ્કેલ લાગી રહ્યું છે. હમણાં પરિવારના કોઈની સાથે વાત કરશો?",
            "pa": "ਤੁਹਾਨੂੰ ਬਹੁਤ ਔਖਾ ਲੱਗ ਰਿਹਾ ਹੈ। ਕੀ ਹੁਣ ਪਰਿਵਾਰ ਵਿੱਚ ਕਿਸੇ ਨਾਲ ਗੱਲ ਕਰਨੀ ਹੈ?",
            "te": "మీకు చాలా కష్టంగా ఉన్నట్టుంది. ఇప్పుడు కుటుంబంలో ఎవరితోనైనా మాట్లాడాలనుకుంటున్నారా?",
            "ml": "നിങ്ങൾക്ക് വളരെ വിഷമമുണ്ടെന്ന് തോന്നുന്നു. ഇപ്പോൾ വീട്ടുകാരിൽ ആരോടെങ്കിലും സംസാരിക്കണോ?",
            "or": "ଆପଣଙ୍କୁ ବହୁତ କଷ୍ଟ ହେଉଛି ଲାଗୁଛି। ଏବେ ପରିବାରର କାହା ସହ କଥା ହେବେ କି?",
        }.get(prefix, "तुम्हाला खूप त्रास होतोय असं वाटतंय. आत्ता घरच्यांपैकी कोणाशी बोलायचं आहे?")
    norm = text.casefold()
    topics = (
        (("भजन", "गाणं", "गाणी", "youtube", "यूट्यूब", "video", "व्हिडिओ", "பாடல்", "ಭಜನೆ", "ভজন", "ભજન", "ਭਜਨ", "భజన", "ഭജൻ"),
         {"mr": "गाणं किंवा भजन", "hi": "गाना या भजन", "en": "a song or devotional video", "ta": "பாடல்", "kn": "ಹಾಡು ಅಥವಾ ಭಜನೆ", "bn": "গান বা ভজন", "gu": "ગીત કે ભજન", "pa": "ਗੀਤ ਜਾਂ ਭਜਨ", "te": "పాట లేదా భజన", "ml": "പാട്ടോ ഭജനയോ", "or": "ଗୀତ ବା ଭଜନ"}),
        (("औषध", "गोळी", "दवा", "medicine", "மருந்து", "ಔಷಧ", "ওষুধ", "દવા", "ਦਵਾਈ", "మందు", "മരുന്ന്"),
         {"mr": "औषध", "hi": "दवा", "en": "medicine", "ta": "மருந்து", "kn": "ಔಷಧ", "bn": "ওষুধ", "gu": "દવા", "pa": "ਦਵਾਈ", "te": "మందు", "ml": "മരുന്ന്", "or": "ଔଷଧ"}),
        (("जेवण", "भूक", "भाजी", "food", "खाना", "உணவு", "ಊಟ", "খাবার", "જમવાનું", "ਖਾਣਾ", "భోజనం", "ഭക്ഷണം"),
         {"mr": "जेवण", "hi": "खाने", "en": "food", "ta": "உணவு", "kn": "ಊಟ", "bn": "খাবার", "gu": "જમવાનું", "pa": "ਖਾਣੇ", "te": "భోజనం", "ml": "ഭക്ഷണം", "or": "ଖାଦ୍ୟ"}),
        (("कॉल", "फोन", "call", "தொலைபேசி", "ಫೋನ್", "ফোন", "ફોન", "ਫ਼ੋਨ", "ఫోన్", "ഫോൺ"),
         {"mr": "फोन", "hi": "फोन", "en": "a phone call", "ta": "தொலைபேசி அழைப்பு", "kn": "ಫೋನ್ ಕರೆ", "bn": "ফোন কল", "gu": "ફોન કૉલ", "pa": "ਫ਼ੋਨ ਕਾਲ", "te": "ఫోన్ కాల్", "ml": "ഫോൺ വിളി", "or": "ଫୋନ କଲ"}),
    )
    topic = ""
    for words, labels in topics:
        if any(word in norm for word in words):
            topic = labels.get(prefix, labels["mr"])
            break
    if not topic:
        topic = text.strip(" .,!?।…")[-48:].strip()
    templates = {
        "mr": "तुम्ही {topic} बद्दल म्हणताय का?", "hi": "क्या आप {topic} के बारे में पूछ रहे हैं?",
        "en": "Are you asking about {topic}?", "ta": "நீங்கள் {topic} பற்றி கேட்கிறீர்களா?",
        "kn": "ನೀವು {topic} ಬಗ್ಗೆ ಕೇಳುತ್ತಿದ್ದೀರಾ?", "bn": "আপনি কি {topic} সম্পর্কে জানতে চাইছেন?",
        "gu": "શું તમે {topic} વિશે પૂછો છો?", "pa": "ਕੀ ਤੁਸੀਂ {topic} ਬਾਰੇ ਪੁੱਛ ਰਹੇ ਹੋ?",
        "te": "మీరు {topic} గురించి అడుగుతున్నారా?", "ml": "നിങ്ങൾ {topic} കുറിച്ചാണോ ചോദിക്കുന്നത്?",
        "or": "ଆପଣ {topic} ବିଷୟରେ ପଚାରୁଛନ୍ତି କି?",
    }
    return templates.get(prefix, templates["mr"]).format(topic=topic)


def reply_or_fallback(
    user_id: int, transcript: str, language: str, http: httpx.Client | None = None
) -> BridgeReply:
    """Like ask_reasoning, but any failure becomes a spoken fallback (mode="fallback")."""
    t0 = time.perf_counter()
    try:
        return ask_reasoning(user_id, transcript, http, language)
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        cause = "rate_limit" if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429 else type(exc).__name__
        log.error("reasoning fallback cause=%s", cause)
        return BridgeReply(
            text=fallback_text(language, transcript),
            mode="safety" if is_emergency(transcript) or is_distress(transcript) else "fallback",
            awaiting_confirmation=False,
            round_trip_ms=(time.perf_counter() - t0) * 1000,
            language=language,
            silent=not bool(fallback_text(language, transcript)),
        )


# Spoken (fixed text) when an idle session ends (only if ARJUN_IDLE_CLOSE_S > 0; hands-free never closes).
# It names the talk button of the elder screen exactly: "बोला".
CLOSING_REPLY = {
    "mr": "ठीक आहे. गरज लागली तर 'बोला' दाबा.",
    "hi": "ठीक है। ज़रूरत हो तो 'बोला' दबाइए।",
    "en": "Okay. If you need me, press 'बोला'.",
}


def closing_text(language: str) -> str:
    return CLOSING_REPLY.get((language or "mr").split("-")[0].lower(), CLOSING_REPLY["mr"])


# ---- T8: queued reminders / medicine prompts (the agent only knows reasoning, never core-api) ----------------
def claim_next_delivery(
    user_id: int, session: str, http: httpx.Client | None = None, media_playing: bool = False,
    call_active: bool = False,
) -> dict | None:  # type: ignore[type-arg]
    """Claim + render the next waiting item for this session, or None (also when reasoning is down)."""
    client = http or _shared_client()
    try:
        r = client.post(
            f"{REASONING_URL}/delivery/next",
            json={"user_id": user_id, "session": session, "media_playing": media_playing,
                  "call_active": call_active},
        )
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("delivery lookup failed (%s): %s", type(exc).__name__, exc)
        return None


def mark_delivery_spoken(user_id: int, delivery_id: int, session: str, http: httpx.Client | None = None) -> None:
    """Report an item as spoken. Call ONLY after playback finished. Raises on failure so the caller can retry."""
    client = http or _shared_client()
    client.post(f"{REASONING_URL}/delivery/{delivery_id}/spoken", json={"user_id": user_id, "session": session}).raise_for_status()


def release_delivery(user_id: int, delivery_id: int, session: str, reason: str, http: httpx.Client | None = None) -> None:
    client = http or _shared_client()
    body = {"user_id": user_id, "session": session, "reason": reason}
    client.post(f"{REASONING_URL}/delivery/{delivery_id}/release", json=body).raise_for_status()


def session_busy(user_id: int, http: httpx.Client | None = None) -> dict | None:  # type: ignore[type-arg]
    """Pending yes/no, recent safety reply, queued items. None when it cannot be asked (never guess)."""
    client = http or _shared_client()
    try:
        r = client.get(f"{REASONING_URL}/session/{user_id}/busy")
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]
    except (httpx.HTTPError, ValueError):
        return None


def media_gate(user_id: int, text: str, http: httpx.Client | None = None) -> dict | None:  # type: ignore[type-arg]
    """While a video plays: is this transcript a safety phrase or a bare control phrase? None when it cannot be asked
    (the caller then passes the transcript on: safety is never ignored)."""
    client = http or _shared_client()
    try:
        r = client.post(f"{REASONING_URL}/media/gate", json={"user_id": user_id, "text": text})
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("media gate unavailable (%s)", type(exc).__name__)
        return None


def media_stopped(user_id: int, http: httpx.Client | None = None) -> None:
    client = http or _shared_client()
    try:
        client.post(f"{REASONING_URL}/media/stopped", json={"user_id": user_id}).raise_for_status()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("media stop state reset failed (%s)", type(exc).__name__)


def video_call_stopped(user_id: int, http: httpx.Client | None = None) -> None:
    client = http or _shared_client()
    try:
        client.post(f"{REASONING_URL}/media/call-stopped", json={"user_id": user_id}).raise_for_status()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("video call state reset failed (%s)", type(exc).__name__)


def report_sound_event(
    user_id: int, label: str, confidence: float, *, escalate: bool = False, http: httpx.Client | None = None
) -> bool:
    """Send labels/score only to reasoning; audio and audio-derived features never leave voice-agent."""
    client = http or _shared_client()
    try:
        path = "/sound-event/escalate" if escalate else "/sound-event"
        payload = {"user_id": user_id}
        if not escalate:
            payload.update({"label": label, "confidence": confidence})
        response = client.post(f"{REASONING_URL}{path}", json=payload)
        response.raise_for_status()
        return True
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("sound event request failed (%s)", type(exc).__name__)
        return False


def should_speak(reply: BridgeReply, stale: bool) -> bool:
    """Speak this reply? An outdated one is dropped: the user has already said something newer, and
    answering the old sentence is how Arjun seemed to reply to the wrong thing (2026-10-24).

    Only plain care and companion replies (and the spoken fallback) may be skipped. Never skipped:
    - mode "safety" (emergency / distress): 112, calling out for help, Elderline. Always spoken.
    - a reply that asks for a yes/no: reasoning has already stored a pending action. Skipping the reply
      would leave an action the user never heard, which a later "हो" would confirm blind. We speak the
      question instead of rejecting the action: the request is kept and the user hears what a "हो" does.
      This relies on reasoning flagging every pending action with awaiting_confirmation
      (tests/test_pending_is_announced.py).
    """
    return stale is False or reply.mode == "safety" or reply.awaiting_confirmation


def endpointing_delay(mode: str) -> float:
    """Seconds of silence before end-of-turn. Companion tolerates longer pauses than care mode.

    PLACEHOLDER values - must be measured on elderly-speaker audio (CLAUDE.md: measure, don't guess).
    """
    return 1.2 if mode == "companion" else 1.0
