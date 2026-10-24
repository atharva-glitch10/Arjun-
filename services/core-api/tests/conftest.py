import os
from datetime import datetime

# core_api.db builds its global engine at import time, so pin the environment first: a shell
# or .env may point DATABASE_URL at the compose-only 'postgres' host or set CORE_API_KEY.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.pop("CORE_API_KEY", None)
os.environ["ARJUN_TESTING"] = "1"  # the only way core-api runs without CORE_API_KEY

import pytest  # noqa: E402
from core_api.db import Base, get_db, make_engine  # noqa: E402
from core_api.main import app, get_now  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

NOW = datetime(2026, 10, 6, 9, 0)


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
