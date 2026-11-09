from core_api.db import Base, make_engine, reconcile_schema
from sqlalchemy import inspect, text


def test_old_tables_are_set_aside_or_extended(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path/'old.db'}")
    with eng.begin() as c:
        # an old check-ins table with a NOT NULL column the model dropped, and an old users table missing new columns
        c.execute(text("CREATE TABLE checkins (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, key VARCHAR NOT NULL)"))
        c.execute(text("INSERT INTO checkins VALUES (1, 1, 'x')"))
    done = reconcile_schema(eng, Base.metadata)
    assert any(d.startswith("checkins -> checkins_old_1") for d in done)
    Base.metadata.create_all(eng)
    insp = inspect(eng)
    assert "checkins_old_1" in insp.get_table_names()  # kept, never dropped
    assert "status" in {c["name"] for c in insp.get_columns("checkins")}
    assert reconcile_schema(eng, Base.metadata) == []  # idempotent
