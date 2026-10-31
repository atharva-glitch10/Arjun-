"""Leave ONE clean synthetic demo user (user 1) in the local database. DRY RUN unless --apply.

  python scripts/clean_demo_db.py                      # print exactly what would be deleted, change nothing
  python scripts/clean_demo_db.py --apply              # back the file up, delete, seed the demo contacts
  python scripts/clean_demo_db.py --also-user1-history # also drop user 1's old test history (see the KEPT list)

Deletes: every user except user 1 with all their data; user 1's junk stories (recognizer repetition) and
distress-event test records. Never deletes user 1, a real-looking story, or anything of a user whose name is not
marked "(synthetic)". Seeds two synthetic contacts for user 1 with obviously made-up placeholder numbers.
"""

import argparse
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "core-api"))

from core_api import models as m  # noqa: E402
from sqlalchemy import create_engine, delete, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

KEEP_USER = 1
# children first, so foreign keys never block a delete
USER_TABLES = [m.MedicineDose, m.Medicine, m.Contact, m.Reminder, m.Appointment, m.StoryMemory, m.PendingAction,
               m.CaregiverRequest, m.Notification, m.DistressEvent, m.TopicDecline, m.Activity,
               m.Wellbeing, m.FeedEvent]
MODELS = {model.__tablename__: model for model in [*USER_TABLES, m.User]}
SEED_CONTACTS = [("राहुल", "मुलगा", "00000 00001"), ("नेहा", "नात", "00000 00002")]  # made up, not real numbers


@dataclass
class Item:
    table: str
    id: int
    user_id: int | None
    summary: str


@dataclass
class Plan:
    delete: list[Item] = field(default_factory=list)
    kept: list[Item] = field(default_factory=list)  # user 1 history that stays unless --also-user1-history
    seed: list[tuple[str, str, str]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _summary(row: object) -> str:
    for attr in ("task", "title", "name", "message", "body", "action_type"):
        v = getattr(row, attr, None)
        if v:
            return str(v)[:40]
    text = getattr(row, "summary", None)
    if text:
        return str(text)[:30]
    return str(getattr(row, "created_at", "") or getattr(row, "due_at", "") or "")


def _is_junk(text: str) -> bool:
    words = text.split()
    return len(words) >= 8 and len(set(words)) / len(words) < 0.4  # "हो हो हो कर कर कर ..." style output


def build_plan(s: Session, also_user1_history: bool = False) -> Plan:
    plan = Plan()
    others = list(s.scalars(select(m.User).where(m.User.id != KEEP_USER).order_by(m.User.id)))
    for u in others:
        if "(synthetic)" not in u.name:
            plan.problems.append(f"user {u.id} is not marked synthetic: {u.name!r}")
    for model in USER_TABLES:
        for u in others:
            for row in s.scalars(select(model).where(model.user_id == u.id)):
                plan.delete.append(Item(model.__tablename__, row.id, u.id, _summary(row)))
    for story in s.scalars(select(m.StoryMemory).where(m.StoryMemory.user_id == KEEP_USER)):
        if _is_junk(story.summary):
            plan.delete.append(Item("story_memories", story.id, KEEP_USER, "recognizer junk: " + story.summary[:24]))
    for ev in s.scalars(select(m.DistressEvent).where(m.DistressEvent.user_id == KEEP_USER)):
        plan.delete.append(Item("distress_events", ev.id, KEEP_USER, f"test event {ev.created_at:%d %b %H:%M}"))
    history = [(m.CaregiverRequest, "caregiver_requests"), (m.Notification, "notifications"),
               (m.PendingAction, "pending_actions")]
    for model, name in history:
        for row in s.scalars(select(model).where(model.user_id == KEEP_USER)):
            (plan.delete if also_user1_history else plan.kept).append(Item(name, row.id, KEEP_USER, _summary(row)))
    plan.delete += [Item("users", u.id, u.id, u.name) for u in others]
    have = {c.name for c in s.scalars(select(m.Contact).where(m.Contact.user_id == KEEP_USER))}
    plan.seed = [c for c in SEED_CONTACTS if c[0] not in have]
    return plan


def apply_plan(s: Session, plan: Plan) -> tuple[int, int]:
    by_table: dict[str, list[int]] = {}
    for item in plan.delete:
        by_table.setdefault(item.table, []).append(item.id)
    order = [model.__tablename__ for model in USER_TABLES] + ["users"]
    for name in order:
        ids = by_table.get(name)
        if ids:
            s.execute(delete(MODELS[name]).where(MODELS[name].id.in_(ids)))
    for name, relation, phone in plan.seed:
        s.add(m.Contact(user_id=KEEP_USER, name=name, relation=relation, phone=phone))
    s.commit()
    return len(plan.delete), len(plan.seed)


def run(db_url: str, apply: bool = False, backup_dir: Path | None = None, also_user1_history: bool = False) -> dict:
    engine = create_engine(db_url)
    with Session(engine) as s:
        plan = build_plan(s, also_user1_history)
        report: dict = {"applied": False, "plan": plan, "deleted": 0, "seeded": 0}
        if not apply:
            return report
        if plan.problems:
            raise SystemExit("refusing to delete: " + "; ".join(plan.problems))
        if db_url.startswith("sqlite:///"):
            src = Path(db_url.removeprefix("sqlite:///"))
            dest = (backup_dir or src.parent) / f"{src.stem}-backup-{datetime.now():%Y%m%d-%H%M%S}.db"
            shutil.copy2(src, dest)
            report["backup"] = str(dest)
        report["deleted"], report["seeded"] = apply_plan(s, plan)
        report["applied"] = True
    return report


def _print(plan: Plan) -> None:
    def group(items: list[Item]) -> None:
        tables: dict[str, list[Item]] = {}
        for i in items:
            tables.setdefault(i.table, []).append(i)
        for t, rows in tables.items():
            print(f"  {t} ({len(rows)})")
            for r in rows:
                print(f"    id {r.id:<3} user {r.user_id}: {r.summary}")

    print("WOULD DELETE:")
    group(plan.delete)
    print("\nKEPT unless you say otherwise (user 1 history; add --also-user1-history to drop it):")
    group(plan.kept)
    print("\nWOULD SEED contacts for user 1:", ", ".join(f"{n} ({r}) {p}" for n, r, p in plan.seed) or "none (already there)")
    for p in plan.problems:
        print("PROBLEM:", p)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # Devanagari names print on a Windows console
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=str(ROOT / "services" / "core-api" / "arjun.db"))
    ap.add_argument("--apply", action="store_true", help="really delete and seed (a backup is made first)")
    ap.add_argument("--also-user1-history", action="store_true")
    args = ap.parse_args(argv)
    report = run(f"sqlite:///{args.db}", args.apply, also_user1_history=args.also_user1_history)
    _print(report["plan"])
    if report["applied"]:
        print(f"\nDONE: deleted {report['deleted']} rows, seeded {report['seeded']} contacts. Backup: {report['backup']}")
    else:
        print("\nDRY RUN: nothing was changed. Add --apply to do it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
