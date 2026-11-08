"""The elder's city (spoken weather): nullable column, safe migration, API round trip."""

from core_api import models as m
from core_api.db import ensure_columns
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session


def _user(client):
    return client.post("/users", json={"name": "Aaji (synthetic)", "language": "mr"}).json()["id"]


def test_city_is_null_by_default_and_round_trips(client):
    uid = _user(client)
    assert client.get(f"/users/{uid}").json()["city"] is None
    assert client.patch(f"/users/{uid}", json={"city": "  Pune "}).json()["city"] == "Pune"
    assert client.get(f"/users/{uid}").json()["city"] == "Pune"


def test_blank_or_null_city_clears_it(client):
    uid = _user(client)
    client.patch(f"/users/{uid}", json={"city": "Pune"})
    assert client.patch(f"/users/{uid}", json={"city": ""}).json()["city"] is None
    client.patch(f"/users/{uid}", json={"city": "Pune"})
    assert client.patch(f"/users/{uid}", json={"city": None}).json()["city"] is None


def test_city_has_a_length_limit(client):
    uid = _user(client)
    assert client.patch(f"/users/{uid}", json={"city": "x" * 81}).status_code == 422


def test_migration_adds_a_nullable_city_column_to_an_old_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as c:
        c.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, language VARCHAR(2) NOT NULL,"
            " wake_time VARCHAR(5) NOT NULL, lunch_time VARCHAR(5) NOT NULL, dinner_time VARCHAR(5) NOT NULL,"
            " interests JSON, opener_start VARCHAR(5) NOT NULL, opener_end VARCHAR(5) NOT NULL,"
            " consent_distress_alert BOOLEAN NOT NULL)"))
        c.execute(text("INSERT INTO users VALUES (1,'Aaji (synthetic)','mr','07:00','13:00','20:00','[]','10:00','18:00',1)"))
    ensure_columns(engine)
    ensure_columns(engine)
    col = next(c for c in inspect(engine).get_columns("users") if c["name"] == "city")
    assert col["nullable"] is True
    with Session(engine) as s:
        assert s.get(m.User, 1).city is None
