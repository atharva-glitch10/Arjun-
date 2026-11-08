import os
from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None):  # type: ignore[no-untyped-def]
    url = url or os.environ.get("DATABASE_URL", "sqlite:///./arjun.db")
    if url.startswith("sqlite"):
        kwargs: dict[str, object] = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
        return create_engine(url, **kwargs)
    return create_engine(url, pool_pre_ping=True)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


# There are no migrations (CLAUDE.md: frozen). `Base.metadata.create_all` makes missing TABLES but never adds a column
# to a table that already exists, so a column added after a database was created is added here, once, at startup.
# (table, column, SQL type, default). Every entry is nullable or has a default, so old rows stay valid.
ADDED_COLUMNS: list[tuple[str, str, str, str | None]] = [
    ("users", "preferred_languages", "JSON", "'[]'"),
    ("users", "breakfast_time", "VARCHAR(5)", "'08:00'"),
    ("users", "snack_time", "VARCHAR(5)", "'17:00'"),
    ("users", "walk_time", "VARCHAR(5)", None),
    ("users", "bp_check_time", "VARCHAR(5)", None),
    ("users", "sugar_check_time", "VARCHAR(5)", None),
    ("users", "sugar_after_time", "VARCHAR(5)", None),
    ("users", "city", "VARCHAR(80)", None),  # elder's city for spoken weather; nullable
    ("users", "daily_checkins", "BOOLEAN", "FALSE"),
    ("users", "honorific", "VARCHAR(60)", "''"),
    ("users", "address_as", "VARCHAR(60)", "''"),
    ("users", "age", "INTEGER", None),
    ("users", "conditions", "JSON", "'[]'"),
    ("users", "speech_style", "JSON", "'{\"rate\":\"normal\",\"volume\":\"normal\",\"simple\"\\:false}'"),
    ("appointments", "weekdays", "JSON", None),
    ("appointments", "start_time", "VARCHAR(5)", None),
    ("appointments", "end_time", "VARCHAR(5)", None),
    ("checkins", "ref", "VARCHAR(160)", "''"),
    ("checkins", "postponed", "INTEGER", "0"),
    ("checkins", "mood", "VARCHAR(12)", "''"),
    ("checkins", "source", "VARCHAR(10)", "'asked'"),
]


def ensure_columns(eng) -> list[str]:  # type: ignore[no-untyped-def]
    """Idempotent "ALTER TABLE ... ADD COLUMN [IF NOT EXISTS]" for every column in ADDED_COLUMNS. A table that does
    not exist yet is skipped (create_all makes it complete). Returns the columns it added."""
    insp = inspect(eng)
    tables = set(insp.get_table_names())
    pg = eng.dialect.name == "postgresql"
    added: list[str] = []
    for table, column, sql_type, default in ADDED_COLUMNS:
        if table not in tables:
            continue
        if column in {c["name"] for c in insp.get_columns(table)}:
            continue
        if default == "FALSE" and not pg:
            default = "0"  # SQLite has no boolean literal in a column default
        ddl = f"ALTER TABLE {table} ADD COLUMN {'IF NOT EXISTS ' if pg else ''}{column} {sql_type}"
        if default is not None:
            ddl += f" NOT NULL DEFAULT {default}"
        with eng.begin() as conn:
            conn.execute(text(ddl))
        added.append(f"{table}.{column}")
    if "users" in tables and "address_as" in {c["name"] for c in inspect(eng).get_columns("users")}:
        with eng.begin() as conn:
            conn.execute(text("UPDATE users SET address_as = 'आजी' WHERE trim(address_as) = '' AND age >= 60"))
            conn.execute(text("UPDATE users SET address_as = trim(substr(name, 1, instr(name || ' ', ' ') - 1)) || 'बाई' WHERE trim(address_as) = ''"))
    return added


def _literal(value: object, pg: bool) -> str | None:
    if isinstance(value, bool):
        return ("TRUE" if value else "FALSE") if pg else ("1" if value else "0")
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None


def reconcile_schema(eng, metadata) -> list[str]:  # type: ignore[no-untyped-def]
    """Bring an old database in line with the models, without migrations (live 2026-11-09: a laptop database made
    weeks ago answered 500 on every check-in, BP and watch read because those tables had changed shape).

    - a model column the table lacks is ADDED (its scalar default, else nullable), so reads work;
    - a table with an old NOT NULL column the model no longer has (inserts would fail), or lacking a column the model
      requires and cannot fill (old rows would be invalid), is RENAMED aside to `<table>_old_<n>` (kept, never dropped) and `create_all` then makes it fresh.
    Returns what it did, for the startup log."""
    insp = inspect(eng)
    existing = set(insp.get_table_names())
    pg = eng.dialect.name == "postgresql"
    done: list[str] = []
    for table in metadata.sorted_tables:
        if table.name not in existing:
            continue
        cols = {c["name"]: c for c in insp.get_columns(table.name)}
        model = {c.name: c for c in table.columns}
        stale = [n for n, c in cols.items()
                 if n not in model and not c.get("nullable", True) and c.get("default") is None
                 and not c.get("autoincrement") and n not in {pk for pk in model if model[pk].primary_key}]
        # a missing column the model requires but cannot fill (NOT NULL, no plain default): old rows would be invalid
        missing_pk = [n for n, c in model.items() if n not in cols and (c.primary_key or (
            not c.nullable and not (c.default is not None and getattr(c.default, "is_scalar", False))))]
        if stale or missing_pk:
            n = 1
            while f"{table.name}_old_{n}" in existing:
                n += 1
            aside = f"{table.name}_old_{n}"
            with eng.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{table.name}" RENAME TO "{aside}"'))
                if not pg:  # SQLite keeps index names with the renamed table; free them for create_all
                    for (idx,) in conn.execute(text(
                            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=:t AND sql IS NOT NULL"),
                            {"t": aside}).fetchall():
                        conn.execute(text(f'DROP INDEX IF EXISTS "{idx}"'))
            existing.add(aside)
            done.append(f"{table.name} -> {aside} (old shape: {', '.join(stale or missing_pk)})")
            continue
        for name, col in model.items():
            if name in cols:
                continue
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{name}" {col.type.compile(dialect=eng.dialect)}'
            default = col.default.arg if col.default is not None and getattr(col.default, "is_scalar", False) else None
            lit = _literal(default, pg) if default is not None else None
            if lit is not None:
                ddl += f" NOT NULL DEFAULT {lit}" if not col.nullable else f" DEFAULT {lit}"
            with eng.begin() as conn:
                conn.execute(text(ddl))
            done.append(f"{table.name}.{name} added")
    return done
