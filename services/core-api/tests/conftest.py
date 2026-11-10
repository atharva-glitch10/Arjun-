import os
from datetime import datetime

# core_api.db builds its global engine at import time, so pin the environment first: a shell
# or .env may point DATABASE_URL at the compose-only 'postgres' host or set CORE_API_KEY.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.pop("CORE_API_KEY", None)
os.environ["ARJUN_TESTING"] = "1"  # the only way core-api runs without CORE_API_KEY
# Telegram alerts are off unless a test turns them on: the shell may carry the real .env values.
os.environ.pop("TELEGRAM_ENABLED", None)
os.environ.pop("TELEGRAM_BOT_TOKEN", None)
os.environ.pop("TELEGRAM_CHAT_ID", None)
os.environ.pop("BASE_URL", None)
os.environ.pop("JOIN_SECRET", None)

import pytest  # noqa: E402
from core_api import baseurl  # noqa: E402
from core_api.db import Base, get_db, make_engine  # noqa: E402
from core_api.main import app, get_now  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

NOW = datetime(2026, 10, 6, 9, 0)


@pytest.fixture(autouse=True)
def _open_signup_for_tests(monkeypatch):
    """Sign-up needs ARJUN_SIGNUP_CODE in real life; the older suites sign up freely. test_auth_hardening.py closes it again."""
    monkeypatch.setenv("ARJUN_ALLOW_OPEN_SIGNUP", "1")
    monkeypatch.delenv("ARJUN_SIGNUP_CODE", raising=False)
    from core_api import auth

    auth.reset_auth_limits_for_tests()
    yield


@pytest.fixture(autouse=True)
def _base_url_probe(monkeypatch):
    """The BASE_URL reachability probe never touches the network in tests: every URL answers 200 unless a test says otherwise."""
    baseurl.reset()
    monkeypatch.setattr(baseurl, "_fetch", lambda url, timeout: 200)
    monkeypatch.delenv("ARJUN_ALLOW_QUICK_TUNNEL", raising=False)
    yield
    baseurl.reset()


@pytest.fixture()
def client():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_now] = lambda: NOW
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def uid(client) -> int:
    r = client.post("/users", json={"name": "Aaji (synthetic)", "interests": ["cooking"]})
    assert r.status_code == 201
    return r.json()["id"]
