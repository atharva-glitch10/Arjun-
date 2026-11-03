import os
import sys
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

# core_api.db builds its global engine at import time, so pin the environment first: a shell
# or .env may point DATABASE_URL at the compose-only 'postgres' host or set CORE_API_KEY.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.pop("CORE_API_KEY", None)
os.environ["ARJUN_TESTING"] = "1"  # the only way core-api runs without CORE_API_KEY
# Never send a real Telegram alert from a test: the shell may carry the developer's .env values.
os.environ.pop("TELEGRAM_ENABLED", None)
os.environ.pop("TELEGRAM_BOT_TOKEN", None)
os.environ.pop("TELEGRAM_CHAT_ID", None)
os.environ.pop("BASE_URL", None)
os.environ.pop("JOIN_SECRET", None)
# The older suites were written for the ask-first flow ("... ठेवू का? हो किंवा नाही"), which stays available
# behind ARJUN_ASK_BEFORE_ACTING=1. The no-question default is tested with ask_first=False explicitly
# (test_no_questions.py and the other new suites).
os.environ.setdefault("ARJUN_ASK_BEFORE_ACTING", "1")

# Integration tests run reasoning against the real core-api app (in-memory SQLite).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core-api"))

from core_api.db import Base, get_db, make_engine  # noqa: E402
from core_api.main import app, get_now  # noqa: E402
from reasoning_svc.core_client import CoreClient  # noqa: E402
from reasoning_svc.turn import TurnEngine  # noqa: E402

NOW = datetime(2026, 10, 6, 9, 0)


@pytest.fixture()
def core_http():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _db():
        with factory() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_now] = lambda: NOW
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def uid(core_http) -> int:
    r = core_http.post(
        "/users",
        json={"name": "Aaji (synthetic)", "language": "mr", "interests": ["cooking"],
              "opener_start": "08:00"},
    )
    return r.json()["id"]


@pytest.fixture()
def engine(core_http) -> TurnEngine:
    return TurnEngine(CoreClient(core_http), evon=None, clock=lambda: NOW)


@pytest.fixture()
def auto(core_http) -> TurnEngine:
    """The production default: no yes/no questions, act at once, "नको" undoes."""
    return TurnEngine(CoreClient(core_http), evon=None, clock=lambda: NOW, ask_first=False)
