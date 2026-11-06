"""Task A: the family-set day schedule (breakfast, snack, walk, BP check), the breakfast medicine anchor and the
safe "add column" step for databases that already exist (there are no migrations)."""

from datetime import datetime

from core_api import models as m
from core_api.db import ensure_columns
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

NOW = datetime(2026, 10, 6, 9, 0)  # a Tuesday


def _heerabai(client) -> int:
    r = client.post(
        "/users",
        json={
            "name": "हीराबाई पवार (synthetic)", "honorific": "हीराबाई", "wake_time": "07:00", "walk_time": "07:30",
            "bp_check_time": "09:30", "breakfast_time": "10:00", "lunch_time": "13:30", "snack_time": "17:30",
            "dinner_time": "20:00", "daily_checkins": True,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_user_age_and_conditions_are_stored_and_editable(client):
    uid = client.post(
        "/users",
        json={"name": "Aaji (synthetic)", "age": 63, "conditions": ["Type 2 diabetes", "High blood pressure"]},
    ).json()["id"]
    u = client.get(f"/users/{uid}").json()
    assert u["age"] == 63 and u["conditions"] == ["Type 2 diabetes", "High blood pressure"]
    r = client.patch(f"/users/{uid}", json={"age": 64, "conditions": ["Type 2 diabetes"]})
    assert r.status_code == 200 and r.json()["age"] == 64 and r.json()["conditions"] == ["Type 2 diabetes"]


def test_address_as_uses_age_default_and_accepts_family_override(client):
    older = client.post("/users", json={"name": "Heerabai (synthetic)", "age": 60}).json()
    younger = client.post("/users", json={"name": "Kamala (synthetic)", "age": 59}).json()
    assert older["address_as"] == "आजी"
    assert younger["address_as"] == "Kamalaबाई"
    changed = client.patch(f"/users/{younger['id']}", json={"address_as": "ताई"}).json()
    assert changed["address_as"] == "ताई"


def test_user_has_the_new_day_times_and_defaults(client):
    uid = client.post("/users", json={"name": "Aaji (synthetic)"}).json()["id"]
    u = client.get(f"/users/{uid}").json()
    assert u["breakfast_time"] == "08:00" and u["snack_time"] == "17:00"
    assert u["walk_time"] is None and u["bp_check_time"] is None
    assert u["daily_checkins"] is False and u["honorific"] == ""


def test_the_family_can_edit_every_marker(client):
    uid = client.post("/users", json={"name": "Aaji (synthetic)"}).json()["id"]
    r = client.patch(
        f"/users/{uid}",
        json={"breakfast_time": "09:15", "snack_time": "16:45", "walk_time": "06:30", "bp_check_time": "08:00",
              "daily_checkins": True, "honorific": "आजी"},
    )
    assert r.status_code == 200
    u = r.json()
    assert (u["breakfast_time"], u["snack_time"], u["walk_time"], u["bp_check_time"]) == (
        "09:15", "16:45", "06:30", "08:00")
    assert u["daily_checkins"] is True and u["honorific"] == "आजी"


def test_a_bad_time_is_refused(client):
    uid = client.post("/users", json={"name": "Aaji (synthetic)"}).json()["id"]
    assert client.patch(f"/users/{uid}", json={"walk_time": "7:5"}).status_code == 422
    assert client.patch(f"/users/{uid}", json={"snack_time": "25:00"}).status_code == 422


def test_day_lists_breakfast_snack_walk_and_bp_as_family_set_markers(client):
    uid = _heerabai(client)
    items = client.get(f"/users/{uid}/day").json()["items"]
    marks = {(i["kind"], i["label"]): i["at"][11:16] for i in items if i["kind"] in ("meal", "walk", "bp", "wake")}
    assert marks == {
        ("wake", "wake"): "07:00", ("walk", "walk"): "07:30", ("bp", "bp"): "09:30",
        ("meal", "breakfast"): "10:00", ("meal", "lunch"): "13:30", ("meal", "snack"): "17:30",
        ("meal", "dinner"): "20:00",
    }


def test_walk_and_bp_markers_are_absent_when_the_family_has_not_set_them(client):
    uid = client.post("/users", json={"name": "Aaji (synthetic)"}).json()["id"]
    kinds = {i["kind"] for i in client.get(f"/users/{uid}/day").json()["items"]}
    assert "walk" not in kinds and "bp" not in kinds


def test_breakfast_anchor_glimepiride_is_1030_and_amlodipine_after_lunch_is_1400(client):
    uid = _heerabai(client)
    g = client.post(
        f"/users/{uid}/medicines",
        json={"name": "Glimepiride", "dose": "1 mg", "anchor": "breakfast", "offset_min": 30},
    )
    a = client.post(
        f"/users/{uid}/medicines",
        json={"name": "Amlodipine", "dose": "2.5 mg", "anchor": "lunch", "offset_min": 30},
    )
    assert g.status_code == 201 and a.status_code == 201, (g.text, a.text)
    assert g.json()["anchor"] == "breakfast"
    future = client.get(f"/users/{uid}/day", params={"on": "2026-10-07"}).json()["items"]
    times = {i["label"]: i["at"][11:16] for i in future if i["kind"] == "medicine"}
    assert times == {"Glimepiride": "10:30", "Amlodipine": "14:00"}


def test_a_medicine_follows_the_breakfast_time_when_the_family_moves_it(client):
    uid = _heerabai(client)
    client.post(f"/users/{uid}/medicines", json={"name": "Glimepiride", "dose": "1 mg", "anchor": "breakfast"})
    client.patch(f"/users/{uid}", json={"breakfast_time": "09:00"})
    future = client.get(f"/users/{uid}/day", params={"on": "2026-10-07"}).json()["items"]
    assert [i["at"][11:16] for i in future if i["kind"] == "medicine"] == ["09:30"]


def test_ensure_columns_adds_the_new_columns_to_an_old_database_and_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as c:  # the shape of the database before task A
        c.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, language VARCHAR(2) NOT NULL,"
            " wake_time VARCHAR(5) NOT NULL, lunch_time VARCHAR(5) NOT NULL, dinner_time VARCHAR(5) NOT NULL,"
            " interests JSON, opener_start VARCHAR(5) NOT NULL, opener_end VARCHAR(5) NOT NULL,"
            " consent_distress_alert BOOLEAN NOT NULL)"))
        c.execute(text(
            "CREATE TABLE appointments (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, title VARCHAR(200) NOT NULL,"
            " starts_at DATETIME NOT NULL, location VARCHAR(200) NOT NULL)"))
        c.execute(text(
            "INSERT INTO users VALUES (1,'Aaji (synthetic)','mr','07:00','13:00','20:00','[]','10:00','18:00',1)"))
    ensure_columns(engine)
    ensure_columns(engine)  # a second start changes nothing
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    assert {"breakfast_time", "snack_time", "walk_time", "bp_check_time", "daily_checkins", "honorific",
            "address_as", "age", "conditions"} <= cols
    acols = {c["name"] for c in inspect(engine).get_columns("appointments")}
    assert {"weekdays", "start_time", "end_time"} <= acols
    with Session(engine) as s:  # the old row is intact and reads with the defaults
        u = s.get(m.User, 1)
        assert u.name == "Aaji (synthetic)" and u.breakfast_time == "08:00" and u.snack_time == "17:00"
        assert u.walk_time is None and u.daily_checkins is False
        assert u.age is None and u.conditions == []
        assert u.address_as == "Aajiबाई"


def test_ensure_columns_skips_tables_that_do_not_exist_yet(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    ensure_columns(engine)  # create_all will make them fresh; nothing to alter, nothing to crash on
