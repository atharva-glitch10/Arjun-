import logging
from typing import Any, Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import config
from .appcmd import MEDIA_CONTROL, parse_app_command
from .core_client import CoreClient, CoreError
from .distress import is_distress, is_emergency
from .evon import EvonClient, Limiter, debug_log, llm_debug_enabled
from .ratelimit import TokenBucket
from .textutil import collapse_repeats
from .turn import TurnEngine
from .wellbeing import Tracker

_OUR_LOGGERS = ("arjun", "reasoning")  # arjun.llm (one line per provider call), reasoning.turn / .wellbeing / ...


def configure_logging() -> None:
    """INFO for our own loggers. Under uvicorn nobody configured them, so every `log.info` (the per-call "arjun.llm"
    line, the per-turn trace) vanished; uvicorn's own loggers are left exactly as they are. Idempotent."""
    for name in _OUR_LOGGERS:
        lg = logging.getLogger(name)
        lg.setLevel(logging.INFO)
        if not lg.handlers and not logging.getLogger().handlers:  # the root logger has none under uvicorn
            h = logging.StreamHandler()
            h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
            lg.addHandler(h)


configure_logging()
app = FastAPI(title="Arjun reasoning")

_engine: TurnEngine | None = None
_tracker: Tracker | None = None
_turn_bucket = TokenBucket(config.TURN_RATE_PER_S, config.TURN_RATE_BURST)


def get_engine() -> TurnEngine:
    global _engine
    if _engine is None:
        s = config.llm_settings()
        llm = (
            EvonClient(
                s.base_url,
                s.model,
                api_key=s.api_key,
                send_template_kwargs=s.send_template_kwargs,
                provider=s.provider,
                max_tokens=s.max_tokens,
                timeout_s=s.timeout_s,
                reasoning_off=s.reasoning_off,
                limiter=Limiter(s.max_concurrent, s.per_minute),
            )
            if s.configured
            else None
        )
        _engine = TurnEngine(CoreClient(), llm, llm_timeout_s=s.timeout_s)
    return _engine


def get_tracker() -> Tracker:
    global _tracker
    if _tracker is None:
        e = get_engine()
        _tracker = Tracker(e.core, e.evon, clock=e.clock)
    return _tracker


class TurnIn(BaseModel):
    user_id: int
    text: str = Field(min_length=1, max_length=2000)
    language_code: str | None = Field(default=None, max_length=16)


class SoundEventIn(BaseModel):
    user_id: int
    label: Literal["cough", "scream", "crying", "bang"]
    confidence: float = Field(ge=0.0, le=1.0)


class SoundEventEscalationIn(BaseModel):
    user_id: int


class TurnOut(BaseModel):
    reply: str
    intent: str
    mode: str
    language: str
    awaiting_confirmation: bool
    screen: str = "reply"
    speech: str = ""  # what the voice says (may carry Timbre v3 tags); empty = say `reply`
    action: dict[str, Any] = {"type": "none", "kind": "", "value": "", "title": ""}  # what the elder screen opens / does
    source: str  # rules | llm
    trace: dict[str, object]
    speech_style: dict[str, object] = {"rate": "normal", "volume": "normal", "simple": False}
    silent: bool = False


@app.get("/health")
def health() -> dict[str, object]:
    s = config.llm_settings()
    return {
        "status": "ok",
        "llm_configured": s.configured,
        "llm_provider": s.provider if s.configured else "none",
        "evon_configured": s.configured and s.provider == "evon",  # old name, kept for the scripts that read it
        "llm_model": s.model if s.configured else "none",
        "ask_before_acting": config.ASK_BEFORE_ACTING,
    }


@app.post("/sound-event")
def sound_event(body: SoundEventIn) -> dict[str, object]:
    """Store only a fixed sound label and confidence; the request never contains audio."""
    try:
        get_engine().core.sound_event(body.user_id, body.label, body.confidence)
    except CoreError as exc:
        raise HTTPException(502, "sound event could not be recorded") from exc
    return {"recorded": True}


@app.post("/sound-event/escalate")
def sound_event_escalate(body: SoundEventEscalationIn) -> dict[str, object]:
    try:
        return get_engine().core.escalate_sound_event(body.user_id)
    except CoreError as exc:
        raise HTTPException(502, "sound event escalation failed") from exc


class DeliveryClaimIn(BaseModel):
    user_id: int
    session: str
    media_playing: bool = False  # a check-in question is not asked while a video / song plays
    call_active: bool = False  # family participant is present; keep all delivery speech silent


class DeliveryDoneIn(DeliveryClaimIn):
    reason: str = "interrupted"  # for release: "tts" (speech failed) | "interrupted"


class DeliveryOut(BaseModel):
    delivery_id: int
    kind: str  # reminder | medicine
    text: str  # the fixed wording to speak (from SQL through a template)
    screen: str  # reminder | medicine
    item: str  # reminder:<id> | dose:<id>
    awaiting_confirmation: bool
    language: str


@app.post("/delivery/next", response_model=DeliveryOut | None)
def delivery_next(body: DeliveryClaimIn) -> DeliveryOut | None:
    """Claim + render the next waiting reminder / medicine prompt for this voice session, or null."""
    try:
        item = get_engine().deliver_next(body.user_id, body.session, body.media_playing, body.call_active)
    except CoreError as exc:
        raise HTTPException(502 if exc.status >= 500 else exc.status, exc.detail) from exc
    return DeliveryOut(**item) if item else None


@app.post("/delivery/{delivery_id}/spoken", status_code=204)
def delivery_spoken(delivery_id: int, body: DeliveryClaimIn) -> None:
    """Call ONLY after playback finished."""
    try:
        get_engine().deliver_spoken(body.user_id, delivery_id, body.session)
    except CoreError as exc:
        raise HTTPException(exc.status, exc.detail) from exc


@app.post("/delivery/{delivery_id}/release", status_code=204)
def delivery_release(delivery_id: int, body: DeliveryDoneIn) -> None:
    try:
        get_engine().deliver_release(body.user_id, delivery_id, body.session, body.reason)
    except CoreError as exc:
        raise HTTPException(exc.status, exc.detail) from exc


@app.get("/session/{user_id}/busy")
def session_busy(user_id: int) -> dict[str, object]:
    """Pending yes/no, recent safety reply, queued deliveries: the voice session must not close while any is true."""
    try:
        return get_engine().busy(user_id)
    except CoreError as exc:
        raise HTTPException(502 if exc.status >= 500 else exc.status, exc.detail) from exc


@app.post("/turn", response_model=TurnOut)
def turn(body: TurnIn, background: BackgroundTasks) -> TurnOut:
    engine = get_engine()
    # "Last talked to Arjun" for the family dashboard: recorded AFTER the reply is sent, so it adds no
    # latency, and on every turn (safety turns included). Time only; the words are never stored.
    wait = _turn_bucket.take(str(body.user_id))
    if wait > 0 and (is_emergency(body.text) or is_distress(body.text)):
        wait = 0  # safety is never rate limited: a busy recognizer must not swallow "छातीत दुखतंय"
    if wait > 0:  # a stuck recognizer loop must not flood core-api or the LLM
        raise HTTPException(429, "too many turns", headers={"Retry-After": str(max(1, round(wait)))})
    background.add_task(engine.note_activity, body.user_id)
    try:
        res = engine.handle(body.user_id, body.text, body.language_code)
    except CoreError as exc:
        raise HTTPException(502 if exc.status >= 500 else exc.status, exc.detail) from exc
    # The family's conversation summary: buffered in memory, sent after the conversation ends.
    if not res.silent:
        background.add_task(
            get_tracker().record, body.user_id, body.text, res.reply, res.intent, res.action.get("title", ""),
        )
    if llm_debug_enabled():
        debug_log(
            "turn", user=body.user_id, stt=body.text, route=res.source, intent=res.intent,
            mode=res.mode, final=res.speech or res.reply, trace=res.trace,
        )
    return TurnOut(**res.__dict__)


class GateIn(BaseModel):
    user_id: int
    text: str = Field(max_length=2000)


class MediaStoppedIn(BaseModel):
    user_id: int


@app.post("/media/gate")
def media_gate(body: GateIn) -> dict[str, bool]:
    """Media mode filter (voice agent): while a video plays, only a SAFETY phrase or a bare control phrase gets through
    without the wake word. Rules only, no core-api, no LLM: it works when everything else is down."""
    text = collapse_repeats(body.text)
    cmd = parse_app_command(text)
    return {
        "safety": is_emergency(text) or is_distress(text),
        "control": cmd is not None and cmd.intent == MEDIA_CONTROL,
    }


@app.post("/media/stopped")
def media_stopped(body: MediaStoppedIn) -> dict[str, bool]:
    get_engine().media_stopped(body.user_id)
    return {"ok": True}


@app.post("/media/call-stopped")
def media_call_stopped(body: MediaStoppedIn) -> dict[str, bool]:
    get_engine().video_call_stopped(body.user_id)
    return {"ok": True}


@app.post("/conversations/flush-idle")
def flush_idle() -> dict[str, int]:
    """Called by the scheduler every tick: send the summary of every conversation that went quiet."""
    return {"sent": get_tracker().flush_idle(), "open": get_tracker().open_count()}


class BriefingOut(BaseModel):
    text: str | None


@app.get("/briefing/{user_id}", response_model=BriefingOut)
def briefing(user_id: int) -> BriefingOut:
    """Day briefing for the scheduler: greeting by time of day + today's items from SQL."""
    try:
        return BriefingOut(text=get_engine().briefing(user_id))
    except CoreError as exc:
        raise HTTPException(502 if exc.status >= 500 else exc.status, exc.detail) from exc


class OpenerOut(BaseModel):
    text: str | None


@app.post("/opener/{user_id}", response_model=OpenerOut)
def opener(user_id: int) -> OpenerOut:
    """Called by the scheduler. At most one opener per window is enforced by the caller + core-api
    decline gate; null text means 'do not open a conversation now'."""
    try:
        return OpenerOut(text=get_engine().opener(user_id))
    except CoreError as exc:
        raise HTTPException(502 if exc.status >= 500 else exc.status, exc.detail) from exc
