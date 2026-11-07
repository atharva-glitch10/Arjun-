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
