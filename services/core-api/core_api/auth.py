"""Phase 1 accounts, memberships, family sessions and paired elder devices."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import models as m
from .clock import local_now
from .db import Base, get_db
from .deps import auth_enabled, testing
from .schemas import ContactIn, UserIn, UserOut, UserPatch

router = APIRouter()
SESSION_COOKIE = "arjun_session"
DEVICE_COOKIE = "arjun_device"
SESSION_SLIDE = timedelta(hours=12)
SESSION_MAX = timedelta(days=30)
DEVICE_MAX_AGE = 10 * 365 * 24 * 60 * 60
_PASSWORDS = PasswordHasher(type=Type.ID, time_cost=3, memory_cost=65536, parallelism=2)
_DUMMY_HASH = _PASSWORDS.hash("not-a-real-account-password")
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_RATE_LOCK = threading.Lock()
_LOGIN_ATTEMPTS: dict[str, list[float]] = {}
_PAIR_ATTEMPTS: dict[str, list[float]] = {}


class SignupIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=256)
    name: str = Field(min_length=1, max_length=100)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not _EMAIL_RE.fullmatch(value):
            raise ValueError("invalid email")
        return value


class LoginIn(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class ParentIn(UserIn):
    contacts: list[ContactIn] = Field(default_factory=list, max_length=50)


class ParentPatch(UserPatch):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    contacts: list[ContactIn] | None = Field(default=None, max_length=50)


class InviteIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class PairDeviceIn(BaseModel):
    code: str = Field(min_length=8, max_length=8, pattern=r"^\d{8}$")
    label: str = Field(default="Elder phone", min_length=1, max_length=100)


def _auth_required() -> None:
    if not auth_enabled():
        raise HTTPException(404, "account authorization is disabled")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(value: str | None) -> bytes | None:
    if not value or len(value) > 128:
        return None
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError):
        return None
    return raw if len(raw) == 32 else None


def _digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def _secure(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"


def _set_cookie(response: Response, request: Request, key: str, value: str, max_age: int) -> None:
    response.set_cookie(
        key, value, max_age=max_age, path="/", httponly=True, secure=_secure(request), samesite="lax"
    )


def _new_session(account_id: int, db: Session, now: datetime) -> tuple[bytes, int]:
    raw = secrets.token_bytes(32)
    row = m.AuthSession(id=raw, account_id=account_id, created_at=now, expires_at=now + SESSION_SLIDE)
    db.add(row)
    db.commit()
    return raw, int(SESSION_SLIDE.total_seconds())


def _account_session(
    request: Request, response: Response, db: Session, *, slide: bool = True
) -> tuple[m.Account, m.AuthSession] | None:
    raw = _unb64(request.cookies.get(SESSION_COOKIE))
    if raw is None:
        return None
    row = db.get(m.AuthSession, raw)
    now = local_now()
    if row is None or row.expires_at <= now or row.created_at + SESSION_MAX <= now:
        return None
    account = db.get(m.Account, row.account_id)
    if account is None:
        return None
    if slide:
        cap = row.created_at + SESSION_MAX
        row.expires_at = min(now + SESSION_SLIDE, cap)
        remaining = max(1, int((row.expires_at - now).total_seconds()))
        _set_cookie(response, request, SESSION_COOKIE, _b64(raw), remaining)
        db.commit()
    request.state.account_id = account.id
    return account, row


def require_account(
    request: Request, response: Response, db: Session = Depends(get_db)
) -> int:
    _auth_required()
    session = _account_session(request, response, db)
    if session is None:
        raise HTTPException(401, "login required")
    return session[0].id


def _membership(db: Session, account_id: int, user_id: int) -> m.Membership | None:
    return db.scalar(
        select(m.Membership).where(m.Membership.account_id == account_id, m.Membership.user_id == user_id)
    )


def _device(request: Request, db: Session, user_id: int, *, touch: bool = True) -> m.Device | None:
    raw = _unb64(request.cookies.get(DEVICE_COOKIE))
    if raw is None:
        return None
    row = db.scalar(select(m.Device).where(m.Device.token_hash == _digest(raw), m.Device.revoked.is_(False)))
    if row is None or row.user_id != user_id:
        return None
    if touch:
        row.last_seen = local_now()
        db.commit()
    return row


def _is_elder_route(method: str, path: str) -> bool:
    """Mirror ELDER_ROUTES in web/server/access.ts."""
    elder = (
        ("GET", r"/users/\d+/(?:deliveries/open|day|reminders|appointments/next|contacts|medicines/due|voice-label)"),
        ("POST", r"/users/\d+/medicine-doses/\d+/(?:taken|snooze)"),
        ("POST", r"/users/\d+/deliveries/\d+/ack"),
        ("POST", r"/users/\d+/calls"),
        ("GET", r"/users/\d+/calls/\d+"),
        ("POST", r"/users/\d+/calls/\d+/end"),
        ("POST", r"/users/\d+/emergency/location"),
    )
    return any(method == mth and re.fullmatch(pattern, path) for mth, pattern in elder)


def _is_family_route(method: str, path: str) -> bool:
    """Mirror the explicit family route set; unlisted user routes are denied."""
    family = (
        ("POST", r"/users"),
        ("GET", r"/users/\d+"),
        ("PATCH", r"/users/\d+"),
        ("GET", r"/users/\d+/(?:reminders|appointments|contacts|app-links|medicines)"),
        ("POST", r"/users/\d+/(?:reminders|appointments|contacts|app-links|medicines)"),
        ("DELETE", r"/users/\d+/(?:reminders|app-links|medicines)/\d+"),
        ("PATCH", r"/users/\d+/medicines/\d+"),
        ("GET", r"/users/\d+/appointments/next"),
        ("GET", r"/users/\d+/facts"),
        ("GET", r"/users/\d+/voices(?:/audit)?"),
        ("GET", r"/users/\d+/emergency-settings"),
        ("PUT", r"/users/\d+/emergency-settings"),
        ("GET", r"/users/\d+/emergency/calls"),
        ("POST", r"/users/\d+/voices"),
        ("POST", r"/users/\d+/voices/\d+/(?:activate|deactivate)"),
        ("DELETE", r"/users/\d+/voices/\d+"),
        ("DELETE", r"/users/\d+/facts/\d+"),
        ("GET", r"/users/\d+/(?:memory-book|caregiver-requests|notifications|activity|wellbeing/today|bp-readings|watch-samples/latest|medicine-doses|checkins/card|deliveries|feed)"),
    )
    return any(method == mth and re.fullmatch(pattern, path) for mth, pattern in family)


def authorize_core_request(request: Request, response: Response, db: Session) -> None:
    """Session/device authorization for browser requests; API-key callers bypass this in deps.require_key."""
    method, path = request.method.upper(), request.url.path
    if path in {"/family/join", "/family/calls/answer", "/family/calls/end"}:
        return  # signed one-time family join token is validated by the route itself
    if path.startswith("/internal/"):
        raise HTTPException(401, "service authentication required")
    match = re.fullmatch(r"/users/(\d+)(?:/.*)?", path)
    if match:
        user_id = int(match.group(1))
        account = _account_session(request, response, db)
        elder_route = _is_elder_route(method, path)
        family_route = _is_family_route(method, path)
        if account is not None and family_route and _membership(db, account[0].id, user_id) is not None:
            return
        if account is not None and family_route and not elder_route:
            raise HTTPException(403, "not authorized for this elder")
        raw_device = _unb64(request.cookies.get(DEVICE_COOKIE))
        if raw_device is not None and elder_route:
            device = db.scalar(select(m.Device).where(m.Device.token_hash == _digest(raw_device), m.Device.revoked.is_(False)))
            if device is None:
                raise HTTPException(401, "paired elder device required")
            if device.user_id != user_id:
                raise HTTPException(403, "device is paired to another elder")
            device.last_seen = local_now()
            db.commit()
            return
        if account is not None and family_route:
            raise HTTPException(403, "not authorized for this elder")
        if account is not None and elder_route:
            raise HTTPException(403, "paired elder device required")
        if account is not None:
            raise HTTPException(403, "route is not available to browser accounts")
        if raw_device is not None:
            raise HTTPException(403, "route is not available to elder devices")
        if account is None and not family_route:
            raise HTTPException(401, "paired elder device required")
        raise HTTPException(401, "login required")
    if path == "/users" and method == "POST":
        account = _account_session(request, response, db)
        if account is None:
            raise HTTPException(401, "login required")
        if db.scalar(select(m.Membership.id).where(m.Membership.account_id == account[0].id)) is None:
            raise HTTPException(403, "no elder memberships")
        request.state.account_id = account[0].id
        return
    if path == "/livekit/token":
        raise HTTPException(401, "paired elder device required")
    # Global read-only dashboard endpoints (e.g. voice metrics/media status) require a family session.
    account = _account_session(request, response, db)
    if account is None:
        raise HTTPException(401, "login required")
    if db.scalar(select(m.Membership.id).where(m.Membership.account_id == account[0].id)) is None:
        raise HTTPException(403, "no elder memberships")


def authorize_websocket(ws, user_id: int, db: Session) -> bool:  # type: ignore[no-untyped-def]
    if "key" in ws.query_params:
        return False
    expected = os.environ.get("CORE_API_KEY")
    given = ws.headers.get("x-api-key") or ""
    if expected and hmac.compare_digest(given.encode(), expected.encode()):
        return True
    raw = _unb64(ws.cookies.get(SESSION_COOKIE))
    if raw is None:
        return False
    row = db.get(m.AuthSession, raw)
    now = local_now()
    if row is None or row.expires_at <= now or row.created_at + SESSION_MAX <= now:
        return False
    if db.get(m.Account, row.account_id) is None or _membership(db, row.account_id, user_id) is None:
        return False
    return True


def require_livekit_access(
    user_id: int,
    request: Request,
    x_api_key: str | None,
    db: Session,
) -> None:
    """Permit service keys or an elder device cookie bound to the requested token user_id."""
    expected = os.environ.get("CORE_API_KEY")
    if expected and hmac.compare_digest((x_api_key or "").encode(), expected.encode()):
        return
    if not auth_enabled():
        if not expected and testing():
            return
        raise HTTPException(503 if not expected else 401, "invalid api key")
    if _device(request, db, user_id) is None:
        raise HTTPException(401, "paired elder device required")


def _remote_key(request: Request, suffix: str) -> str:
    ip = request.client.host if request.client else "unknown"
    return _digest(f"{ip}:{suffix}")


def _within_rate(table: dict[str, list[float]], key: str, limit: int, window: int) -> bool:
    now = time.monotonic()
    cutoff = now - window
    with _RATE_LOCK:
        attempts = [value for value in table.get(key, []) if value > cutoff]
        if len(attempts) >= limit:
            table[key] = attempts
            return False
        attempts.append(now)
        table[key] = attempts
        if len(table) > 20_000:
            for old_key in [k for k, values in table.items() if not values or values[-1] <= cutoff][:5000]:
                table.pop(old_key, None)
        return True


def reset_auth_limits_for_tests() -> None:
    with _RATE_LOCK:
        _LOGIN_ATTEMPTS.clear()
        _PAIR_ATTEMPTS.clear()


def _login_error() -> HTTPException:
    return HTTPException(401, "invalid email or password", headers={"Cache-Control": "no-store"})


@router.post("/auth/signup", status_code=201)
def signup(body: SignupIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict[str, object]:
    _auth_required()
    email = body.email
    if db.scalar(select(m.Account.id).where(m.Account.email == email)) is not None:
        raise HTTPException(409, "email unavailable")
    now = local_now()
    account = m.Account(email=email, name=body.name.strip(), password_hash=_PASSWORDS.hash(body.password), created_at=now)
    db.add(account)
    db.flush()
    raw, age = _new_session(account.id, db, now)
    _set_cookie(response, request, SESSION_COOKIE, _b64(raw), age)
    response.headers["Cache-Control"] = "no-store"
    return {"id": account.id, "email": account.email, "name": account.name, "elders": []}


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict[str, object]:
    _auth_required()
    key = _remote_key(request, body.email)
    if not _within_rate(_LOGIN_ATTEMPTS, key, 5, 60):
        raise HTTPException(429, "invalid email or password", headers={"Retry-After": "60", "Cache-Control": "no-store"})
    account = db.scalar(select(m.Account).where(m.Account.email == body.email))
    password_hash = account.password_hash if account else _DUMMY_HASH
    try:
        valid = _PASSWORDS.verify(password_hash, body.password)
    except (VerifyMismatchError, InvalidHashError):
        valid = False
    if not valid or account is None:
        raise _login_error()
    now = local_now()
    raw, age = _new_session(account.id, db, now)
    _set_cookie(response, request, SESSION_COOKIE, _b64(raw), age)
    response.headers["Cache-Control"] = "no-store"
    return {"id": account.id, "email": account.email, "name": account.name}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> Response:
    _auth_required()
    raw = _unb64(request.cookies.get(SESSION_COOKIE))
    if raw is not None:
        row = db.get(m.AuthSession, raw)
        if row is not None:
            db.delete(row)
            db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=_secure(request), samesite="lax")
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/auth/me")
def auth_me(account_id: int = Depends(require_account), db: Session = Depends(get_db)) -> dict[str, object]:
    account = db.get(m.Account, account_id)
    assert account is not None
    rows = db.execute(
        select(m.User.id, m.User.name, m.Membership.role, m.User.language)
        .join(m.Membership, m.Membership.user_id == m.User.id)
        .where(m.Membership.account_id == account_id)
        .order_by(m.User.id)
    ).all()
    return {
        "account": {"id": account.id, "email": account.email, "name": account.name},
        "elders": [{"id": row.id, "name": row.name, "role": row.role, "language": row.language} for row in rows],
    }


@router.get("/parents")
def list_parents(account_id: int = Depends(require_account), db: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = db.execute(
        select(m.User, m.Membership.role).join(m.Membership, m.Membership.user_id == m.User.id)
        .where(m.Membership.account_id == account_id).order_by(m.User.id)
    ).all()
    return [{**UserOut.model_validate(user).model_dump(), "role": role} for user, role in rows]


@router.post("/parents", status_code=201)
def create_parent(body: ParentIn, account_id: int = Depends(require_account), db: Session = Depends(get_db)) -> dict[str, object]:
    values = body.model_dump(exclude={"contacts"})
    if not values.get("address_as"):
        first = values["name"].split()[0].split("(", 1)[0].strip()
        values["address_as"] = "आजी" if values.get("age") is not None and values["age"] >= 60 else f"{first}बाई"
    parent = m.User(**values)
    db.add(parent)
    db.flush()
    db.add(m.Membership(account_id=account_id, user_id=parent.id, role="owner"))
    for contact in body.contacts:
        db.add(m.Contact(user_id=parent.id, **contact.model_dump()))
    db.commit()
    db.refresh(parent)
    return {**UserOut.model_validate(parent).model_dump(),
            "contacts": [c.model_dump() for c in body.contacts], "role": "owner"}


def _parent_or_404(db: Session, account_id: int, parent_id: int) -> tuple[m.User, m.Membership]:
    row = db.execute(
        select(m.User, m.Membership).join(m.Membership, m.Membership.user_id == m.User.id)
        .where(m.User.id == parent_id, m.Membership.account_id == account_id)
    ).first()
    if row is None:
        raise HTTPException(404, "elder not found")
    return row[0], row[1]


@router.get("/parents/{parent_id}")
def get_parent(parent_id: int, account_id: int = Depends(require_account), db: Session = Depends(get_db)) -> dict[str, object]:
    parent, membership = _parent_or_404(db, account_id, parent_id)
    contacts = list(db.scalars(select(m.Contact).where(m.Contact.user_id == parent_id).order_by(m.Contact.id)))
    return {**UserOut.model_validate(parent).model_dump(),
            "contacts": [{"id": c.id, "name": c.name, "relation": c.relation, "phone": c.phone} for c in contacts], "role": membership.role}


@router.patch("/parents/{parent_id}")
def patch_parent(
    parent_id: int, body: ParentPatch, account_id: int = Depends(require_account), db: Session = Depends(get_db)
) -> dict[str, object]:
    parent, _ = _parent_or_404(db, account_id, parent_id)
    values = body.model_dump(exclude_unset=True, exclude={"contacts"})
    for key, value in values.items():
        if value is not None or key in {"walk_time", "bp_check_time", "sugar_check_time", "sugar_after_time"}:
            setattr(parent, key, value)
    if body.contacts is not None:
        db.execute(delete(m.Contact).where(m.Contact.user_id == parent_id))
        for contact in body.contacts:
            db.add(m.Contact(user_id=parent_id, **contact.model_dump()))
    db.commit()
    db.refresh(parent)
    contacts = list(db.scalars(select(m.Contact).where(m.Contact.user_id == parent_id).order_by(m.Contact.id)))
    return {**UserOut.model_validate(parent).model_dump(),
            "contacts": [{"id": c.id, "name": c.name, "relation": c.relation, "phone": c.phone} for c in contacts]}


@router.delete("/parents/{parent_id}", status_code=204)
def delete_parent(parent_id: int, account_id: int = Depends(require_account), db: Session = Depends(get_db)) -> Response:
    parent, membership = _parent_or_404(db, account_id, parent_id)
    if membership.role != "owner":
        raise HTTPException(403, "owner membership required")
    user_id = parent.id
    # Delete child rows first, using metadata so newly added per-user tables participate automatically.
    for table in reversed(Base.metadata.sorted_tables):
        if table.name != m.User.__tablename__ and "user_id" in table.c:
            db.execute(delete(table).where(table.c.user_id == user_id))
    db.delete(parent)
    db.commit()
    return Response(status_code=204)


@router.post("/parents/{parent_id}/invite", status_code=201)
def create_invite(
    parent_id: int, request: Request, account_id: int = Depends(require_account), db: Session = Depends(get_db)
) -> dict[str, object]:
    _parent_or_404(db, account_id, parent_id)
    raw = secrets.token_urlsafe(32)
    expires = local_now() + timedelta(days=7)
    db.add(m.Invite(token_hash=_digest(raw), user_id=parent_id, expires_at=expires, used=False))
    db.commit()
    base = os.environ.get("BASE_URL", "").rstrip("/")
    url = f"{base}/?view=invite&token={raw}" if base else f"/?view=invite&token={raw}"
    return {"url": url, "expires_at": expires.isoformat()}


@router.post("/auth/accept-invite")
def accept_invite(
    body: InviteIn, account_id: int = Depends(require_account), db: Session = Depends(get_db)
) -> dict[str, object]:
    now = local_now()
    row = db.scalar(select(m.Invite).where(m.Invite.token_hash == _digest(body.token)))
    if row is None or row.used or row.expires_at <= now:
        raise HTTPException(400, "invite is invalid or expired")
    if _membership(db, account_id, row.user_id) is None:
        db.add(m.Membership(account_id=account_id, user_id=row.user_id, role="family"))
    row.used = True
    db.commit()
    return {"accepted": True, "user_id": row.user_id}


@router.post("/parents/{parent_id}/pairing", status_code=201)
def create_pairing(
    parent_id: int, account_id: int = Depends(require_account), db: Session = Depends(get_db)
) -> dict[str, object]:
    _parent_or_404(db, account_id, parent_id)
    code = f"{secrets.randbelow(100_000_000):08d}"
    expires = local_now() + timedelta(minutes=15)
    db.add(m.PairingCode(code_hash=_digest(code), user_id=parent_id, expires_at=expires, used=False))
    db.commit()
    base = os.environ.get("BASE_URL", "").rstrip("/")
    link = f"{base}/?pair={code}" if base else f"/?pair={code}"
    return {"code": code, "url": link, "qr_data": link, "expires_at": expires.isoformat()}


@router.post("/devices/pair")
def pair_device(body: PairDeviceIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict[str, object]:
    _auth_required()
    remote = request.client.host if request.client else "unknown"
    if not _within_rate(_PAIR_ATTEMPTS, _digest(remote), 10, 60):
        raise HTTPException(429, "pairing code invalid or expired", headers={"Retry-After": "60"})
    now = local_now()
    row = db.scalar(select(m.PairingCode).where(m.PairingCode.code_hash == _digest(body.code)))
    if row is None or row.used or row.expires_at <= now:
        raise HTTPException(400, "pairing code invalid or expired")
    raw = secrets.token_bytes(32)
    device = m.Device(user_id=row.user_id, token_hash=_digest(raw), label=body.label.strip(), last_seen=now, revoked=False)
    row.used = True
    db.add(device)
    db.commit()
    token = _b64(raw)
    _set_cookie(response, request, DEVICE_COOKIE, token, DEVICE_MAX_AGE)
    response.headers["Cache-Control"] = "no-store"
    return {"user_id": device.user_id, "device_token": token, "expires_in": DEVICE_MAX_AGE}


@router.get("/parents/{parent_id}/devices")
def list_devices(parent_id: int, account_id: int = Depends(require_account), db: Session = Depends(get_db)) -> list[dict[str, object]]:
    _parent_or_404(db, account_id, parent_id)
    devices = db.scalars(select(m.Device).where(m.Device.user_id == parent_id).order_by(m.Device.id))
    return [{"id": row.id, "label": row.label, "last_seen": row.last_seen, "revoked": row.revoked} for row in devices]


@router.delete("/parents/{parent_id}/devices/{device_id}", status_code=204)
def revoke_device(
    parent_id: int, device_id: int, account_id: int = Depends(require_account), db: Session = Depends(get_db)
) -> Response:
    _parent_or_404(db, account_id, parent_id)
    device = db.scalar(select(m.Device).where(m.Device.id == device_id, m.Device.user_id == parent_id))
    if device is None:
        raise HTTPException(404, "device not found")
    device.revoked = True
    db.commit()
    return Response(status_code=204)
