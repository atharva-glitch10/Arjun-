"""Consent-first cloned voices (Gnani voice-clone API, docs.gnani.ai/api/VC).

Flow: the family records 5-30 s of the voice owner, the owner's consent is confirmed, core-api sends the clip to
POST {GNANI_TTS_BASE}/api/v1/tts/voice-clone/embeddings once and stores ONLY the encrypted speaker_embedding.
The voice-agent fetches the active embedding over /internal (API key only) and passes it to the Voice Cloned TTS
endpoint. The elder's screen shows whose voice is speaking (/voice-label).
"""

import base64
import binascii
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import models as m
from .db import get_db
from .deps import require_key

router = APIRouter(dependencies=[Depends(require_key)])

GNANI_BASE = os.environ.get("GNANI_TTS_BASE_URL", "https://api.vachana.ai").rstrip("/")
MAX_AUDIO_BYTES = 6 * 1024 * 1024  # ~60 s of compressed speech; Gnani recommends 5-30 s
MIN_AUDIO_BYTES = 8 * 1024
CONSENT_TEXT = (
    "I am the person whose voice this is, or I have their clear permission. I agree that Arjun may speak in this "
    "voice to my family member in friendly conversation only, never for emergency, medicine or money messages, and "
    "that it can be deleted at any time."
)


class VoiceIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    relation: str = Field(default="", max_length=40)
    consent: bool
    consent_by: str = Field(min_length=1, max_length=120)
    audio_base64: str = Field(min_length=1)
    mime: str = Field(default="audio/webm", max_length=60)


class VoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    relation: str
    consent_by: str
    consented_at: object
    active: bool
    use_count: int
    last_used_at: object | None


def _fernet():  # type: ignore[no-untyped-def]
    key = os.environ.get("VOICE_CLONE_KEY", "").strip()
    if not key:
        raise HTTPException(503, "voice cloning is not configured (VOICE_CLONE_KEY)")
    from cryptography.fernet import Fernet

    try:
        return Fernet(key.encode())
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(503, "VOICE_CLONE_KEY is not a valid Fernet key") from exc


def create_embedding(audio: bytes, mime: str) -> dict[str, object]:
    """Gnani Voice Clone Embeddings -> {"embedding", "shape", "dtype"}. Replaced in tests (no network)."""
    key = os.environ.get("GNANI_API_KEY", "").strip()
    if not key:
        raise HTTPException(503, "GNANI_API_KEY is not configured")
    ext = {"audio/wav": "wav", "audio/x-wav": "wav", "audio/mpeg": "mp3", "audio/ogg": "ogg", "audio/mp4": "m4a"}
    filename = "reference." + ext.get(mime.split(";")[0].strip(), "webm")
    try:
        res = httpx.post(
            f"{GNANI_BASE}/api/v1/tts/voice-clone/embeddings",
            headers={"X-API-Key-ID": key},
            files={"audio_file": (filename, audio, mime)},
            timeout=60.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Gnani voice-clone unreachable ({type(exc).__name__})") from exc
    if res.status_code != 200:
        raise HTTPException(502, f"Gnani voice-clone error {res.status_code}")
    data = (res.json().get("data") or {}).get("voice_clone_embedding") or {}
    if not isinstance(data.get("embedding"), str) or not data["embedding"]:
        raise HTTPException(502, "Gnani voice-clone returned no embedding")
    return {"embedding": data["embedding"], "shape": list(data.get("shape") or []), "dtype": str(data.get("dtype") or "")}


def _audit(db: Session, voice: m.ClonedVoice, event: str) -> None:
    db.add(m.ClonedVoiceAudit(user_id=voice.user_id, voice_id=voice.id, voice_name=voice.name, event=event))


def _voice(db: Session, user_id: int, voice_id: int) -> m.ClonedVoice:
    voice = db.get(m.ClonedVoice, voice_id)
    if voice is None or voice.user_id != user_id:
        raise HTTPException(404, "voice not found")
    return voice


@router.get("/users/{user_id}/voices", response_model=list[VoiceOut])
def list_voices(user_id: int, db: Session = Depends(get_db)) -> list[m.ClonedVoice]:
    return list(db.scalars(select(m.ClonedVoice).where(m.ClonedVoice.user_id == user_id).order_by(m.ClonedVoice.id)))


@router.post("/users/{user_id}/voices", response_model=VoiceOut, status_code=201)
def add_voice(user_id: int, body: VoiceIn, db: Session = Depends(get_db)) -> m.ClonedVoice:
    if db.get(m.User, user_id) is None:
        raise HTTPException(404, "user not found")
    if body.consent is not True:
        raise HTTPException(422, "the voice owner's consent is required")
    fernet = _fernet()
    try:
        audio = base64.b64decode(body.audio_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, "audio is not valid base64") from exc
    if len(audio) < MIN_AUDIO_BYTES:
        raise HTTPException(422, "recording is too short; record 10-30 seconds of clear speech")
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "recording is too long; 10-30 seconds is enough")
    emb = create_embedding(audio, body.mime)
    del audio  # the reference recording is never stored
    has_active = db.scalar(select(m.ClonedVoice.id).where(m.ClonedVoice.user_id == user_id, m.ClonedVoice.active))
    voice = m.ClonedVoice(
        user_id=user_id, name=body.name.strip(), relation=body.relation.strip(), consent_by=body.consent_by.strip(),
        consent_text=CONSENT_TEXT, embedding_enc=fernet.encrypt(str(emb["embedding"]).encode()),
        shape=emb["shape"], dtype=emb["dtype"], active=has_active is None,
    )
    db.add(voice)
    db.flush()
    _audit(db, voice, "added")
    if voice.active:
        _audit(db, voice, "activated")
    db.commit()
    db.refresh(voice)
    return voice


@router.post("/users/{user_id}/voices/{voice_id}/activate", response_model=VoiceOut)
def activate_voice(user_id: int, voice_id: int, db: Session = Depends(get_db)) -> m.ClonedVoice:
    voice = _voice(db, user_id, voice_id)
    db.execute(update(m.ClonedVoice).where(m.ClonedVoice.user_id == user_id).values(active=False))
    voice.active = True
    _audit(db, voice, "activated")
    db.commit()
    db.refresh(voice)
    return voice


@router.post("/users/{user_id}/voices/{voice_id}/deactivate", response_model=VoiceOut)
def deactivate_voice(user_id: int, voice_id: int, db: Session = Depends(get_db)) -> m.ClonedVoice:
    voice = _voice(db, user_id, voice_id)
    voice.active = False
    _audit(db, voice, "deactivated")
    db.commit()
    db.refresh(voice)
    return voice


@router.delete("/users/{user_id}/voices/{voice_id}", status_code=204)
def delete_voice(user_id: int, voice_id: int, db: Session = Depends(get_db)) -> Response:
    voice = _voice(db, user_id, voice_id)
    _audit(db, voice, "deleted")
    db.delete(voice)
    db.commit()
    return Response(status_code=204)


@router.get("/users/{user_id}/voice-label")
def voice_label(user_id: int, db: Session = Depends(get_db)) -> dict[str, str | None]:
    """What the elder screen shows: whose voice Arjun may speak in right now (None = Arjun's own)."""
    voice = db.scalar(select(m.ClonedVoice).where(m.ClonedVoice.user_id == user_id, m.ClonedVoice.active))
    return {"name": voice.name if voice else None, "relation": voice.relation if voice else None}


@router.get("/users/{user_id}/voices/audit")
def voice_audit(user_id: int, db: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = db.scalars(
        select(m.ClonedVoiceAudit).where(m.ClonedVoiceAudit.user_id == user_id)
        .order_by(m.ClonedVoiceAudit.id.desc()).limit(50)
    )
    return [{"voice_id": r.voice_id, "voice_name": r.voice_name, "event": r.event, "at": r.at} for r in rows]


@router.get("/internal/users/{user_id}/cloned-voice")
def internal_active_voice(user_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Service-only (API key): the decrypted active embedding for the voice-agent. 404 = speak as Arjun."""
    voice = db.scalar(select(m.ClonedVoice).where(m.ClonedVoice.user_id == user_id, m.ClonedVoice.active))
    if voice is None:
        raise HTTPException(404, "no active cloned voice")
    embedding = _fernet().decrypt(voice.embedding_enc).decode()
    return {"voice_id": voice.id, "name": voice.name, "embedding": embedding, "shape": voice.shape, "dtype": voice.dtype}


@router.post("/internal/users/{user_id}/cloned-voice/{voice_id}/used", status_code=204)
def internal_voice_used(user_id: int, voice_id: int, db: Session = Depends(get_db)) -> Response:
    voice = db.get(m.ClonedVoice, voice_id)
    if voice is not None and voice.user_id == user_id:
        from .deps import local_now

        voice.use_count += 1
        voice.last_used_at = local_now()
        _audit(db, voice, "used")
        db.commit()
    return Response(status_code=204)
