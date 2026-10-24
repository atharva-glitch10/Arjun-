from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import config
from .core_client import CoreClient, CoreError
from .evon import EvonClient
from .turn import TurnEngine

app = FastAPI(title="Arjun reasoning")

_engine: TurnEngine | None = None


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
            )
            if s.configured
            else None
        )
        _engine = TurnEngine(CoreClient(), llm)
    return _engine


class TurnIn(BaseModel):
    user_id: int
    text: str = Field(min_length=1, max_length=2000)


class TurnOut(BaseModel):
    reply: str
    intent: str
    mode: str
    language: str
    awaiting_confirmation: bool
    screen: str = "reply"
    source: str
    trace: dict[str, object]


@app.get("/health")
def health() -> dict[str, object]:
    s = config.llm_settings()
    return {
        "status": "ok",
        "llm_configured": s.configured,
        "llm_provider": s.provider if s.configured else "none",
        "evon_configured": s.configured and s.provider == "evon",  # old name, kept for the scripts that read it
    }


@app.post("/turn", response_model=TurnOut)
def turn(body: TurnIn) -> TurnOut:
    try:
        res = get_engine().handle(body.user_id, body.text)
    except CoreError as exc:
        raise HTTPException(502 if exc.status >= 500 else exc.status, exc.detail) from exc
    return TurnOut(**res.__dict__)


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
