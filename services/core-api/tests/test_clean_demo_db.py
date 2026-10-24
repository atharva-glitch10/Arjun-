"""scripts/clean_demo_db.py: leave ONE clean synthetic demo user. Runs only on a temporary database here."""

import importlib.util
from datetime import datetime
from pathlib import Path

import pytest
from core_api import models as m
from core_api.db import Base
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("clean_demo_db", ROOT / "scripts" / "clean_demo_db.py")
clean = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clean)

JUNK = "हो हो हो " + ("कर " * 21).strip()
REAL_STORY = "आम्ही लहानपणी गावात रोज नदीवर जायचो आणि आजी आम्हाला भाकरी द्यायची आणि गोष्टी सांगायची"


@pytest.fixture()
def db(tmp_path):
    """A copy of the shape of the real demo database on 2026-10-24."""
    url = f"sqlite:///{tmp_path / 'demo.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all([
            m.User(id=1, name="Demo Aaji (synthetic)"), m.User(id=2, name="Demo Aaji (synthetic)"),
            m.User(id=3, name="Demo Aaji (synthetic)"), m.User(id=4, name="Aaji (synthetic)"),
        ])
        s.flush()
        s.add_all([
            m.Reminder(user_id=1, task="डॉक्टरांकडे जायचं", due_at=datetime(2026, 10, 25, 10), status="pending"),
            m.Reminder(user_id=3, task="old", due_at=datetime(2026, 10, 13, 23, 30), status="fired"),
            m.StoryMemory(user_id=1, summary=JUNK), m.StoryMemory(user_id=1, summary=REAL_STORY),
            m.StoryMemory(user_id=4, summary="another users story"),
            m.DistressEvent(user_id=1, created_at=datetime(2026, 10, 24, 14, 14)),
            m.DistressEvent(user_id=1, created_at=datetime(2026, 10, 24, 17, 16)),
            m.DistressEvent(user_id=4, created_at=datetime(2026, 10, 18, 17, 1)),
            m.PendingAction(user_id=1, action_type="CREATE_REMINDER", payload={}, status="confirmed"),
            m.PendingAction(user_id=4, action_type="REQUEST_CAREGIVER", payload={}, status="pending"),
            m.CaregiverRequest(user_id=1, message="Please call me.", created_at=datetime(2026, 10, 13, 19, 53)),
            m.Notification(user_id=1, kind="caregiver_request", body="Please call me.",
                           created_at=datetime(2026, 10, 13, 19, 53)),
            m.Contact(user_id=2, name="x", relation="y", phone="1"),
        ])
        s.commit()
    return url


def count(url, model, **where):
    with Session(create_engine(url)) as s:
        q = select(func.count()).select_from(model)
        for k, v in where.items():
            q = q.where(getattr(model, k) == v)
        return s.scalar(q)


def test_plan_lists_exactly_the_agreed_rows_and_changes_nothing(db):
    with Session(create_engine(db)) as s:
        plan = clean.build_plan(s)
    by_table = {}
    for item in plan.delete:
        by_table.setdefault(item.table, []).append(item.id)
    assert sorted(i.id for i in plan.delete if i.table == "users") == [2, 3, 4]
    assert len(by_table["story_memories"]) == 2  # the junk story of user 1 + user 4's story; the real one stays
    assert len(by_table["distress_events"]) == 3  # both user-1 test events + user 4's
    assert len(by_table["reminders"]) == 1  # user 3 old 13 Oct reminder; user 1 pending one stays
    assert [c[0] for c in plan.seed] == ["राहुल", "नेहा"]
    assert count(db, m.User) == 4 and count(db, m.StoryMemory) == 3  # a plan is a read


def test_the_real_story_the_reminder_and_user_one_stay(db):
    with Session(create_engine(db)) as s:
        plan = clean.build_plan(s)
        deleted = {(i.table, i.id) for i in plan.delete}
        real = s.scalar(select(m.StoryMemory).where(m.StoryMemory.summary == REAL_STORY))
        keep_rem = s.scalar(select(m.Reminder).where(m.Reminder.user_id == 1))
    assert ("story_memories", real.id) not in deleted and ("reminders", keep_rem.id) not in deleted
    assert ("users", 1) not in deleted


def test_user_one_history_is_kept_unless_asked_and_is_listed_as_kept(db):
    with Session(create_engine(db)) as s:
        plan = clean.build_plan(s)
        assert any(i.table == "caregiver_requests" for i in plan.kept) and any(i.table == "pending_actions" for i in plan.kept)
        assert not any(i.user_id == 1 and i.table in ("caregiver_requests", "notifications", "pending_actions") for i in plan.delete)
        also = clean.build_plan(s, also_user1_history=True)
    assert any(i.user_id == 1 and i.table == "pending_actions" for i in also.delete)
    assert any(i.user_id == 1 and i.table == "caregiver_requests" for i in also.delete)


def test_apply_deletes_cleans_seeds_and_backs_up_first(db, tmp_path):
    report = clean.run(db, apply=True, backup_dir=tmp_path)
    assert report["applied"] and Path(report["backup"]).exists()
    assert count(db, m.User) == 1 and count(db, m.Reminder) == 1
    assert count(db, m.StoryMemory) == 1 and count(db, m.DistressEvent) == 0
    with Session(create_engine(db)) as s:
        contacts = list(s.scalars(select(m.Contact).where(m.Contact.user_id == 1)))
    assert [(c.name, c.relation) for c in contacts] == [("राहुल", "मुलगा"), ("नेहा", "नात")]
    assert all(c.phone.startswith("00000 ") for c in contacts)  # obviously made-up placeholders


def test_dry_run_is_the_default_and_touches_nothing(db, tmp_path):
    report = clean.run(db, apply=False, backup_dir=tmp_path)
    assert not report["applied"] and "backup" not in report
    assert count(db, m.User) == 4 and count(db, m.Contact) == 1


def test_a_second_apply_is_a_no_op_and_never_duplicates_contacts(db, tmp_path):
    clean.run(db, apply=True, backup_dir=tmp_path)
    again = clean.run(db, apply=True, backup_dir=tmp_path)
    assert again["deleted"] == 0 and again["seeded"] == 0
    assert count(db, m.Contact, user_id=1) == 2


def test_it_refuses_to_delete_anything_that_is_not_a_synthetic_demo_user(db, tmp_path):
    with Session(create_engine(db)) as s:
        s.get(m.User, 3).name = "Real Person Name"
        s.commit()
    with pytest.raises(SystemExit) as exc:
        clean.run(db, apply=True, backup_dir=tmp_path)
    assert "not marked synthetic" in str(exc.value)
    assert count(db, m.User) == 4  # nothing was deleted
