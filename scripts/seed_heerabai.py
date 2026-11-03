"""Seed the synthetic Heerabai demo user through core-api. Dry run unless --apply."""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

USER_ID = 1
USER_NAME = "हीराबाई पवार (synthetic)"
USER_PROFILE = {
    "language": "mr",
    "wake_time": "07:00",
    "lunch_time": "13:30",
    "dinner_time": "20:00",
    "interests": ["गाणी", "भजन", "स्वयंपाक"],
    "opener_start": "09:00",
    "opener_end": "19:00",
    "consent_distress_alert": True,
}
CONTACT = {"name": "चंद्रकांत", "relation": "मुलगा", "phone": "00000 00003"}
MEDICINES = (
    {
        "name": "Glimepiride",
        "dose": "1 mg",
        "anchor": "fixed",
        "time": "10:30",
        "max_reminders": 3,
        "repeat_minutes": 15,
        "window_min": 30,
    },
    {
        "name": "Amlodipine",
        "dose": "2.5 mg",
        "anchor": "fixed",
        "time": "14:00",
        "max_reminders": 3,
        "repeat_minutes": 15,
        "window_min": 30,
    },
)
REMINDERS = (("चालायला जा", "07:30"), ("बीपी तपासा", "09:30"))
LOCAL_TZ = timezone(timedelta(hours=5, minutes=30))


class SeedError(Exception):
    pass


class ApiError(SeedError):
    def __init__(self, status: int, method: str, path: str):
        self.status = status
        self.method = method
        self.path = path
        super().__init__(f"core-api returned HTTP {status} for {method} {path}")


def load_api_key() -> str:
    if not os.environ.get("CORE_API_KEY", "").strip():
        env_path = Path(__file__).resolve().parents[1] / ".env"
        if env_path.exists():
            for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:].lstrip()
                name, separator, value = line.partition("=")
                if not separator or name.strip() != "CORE_API_KEY":
                    continue
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                    value = value[1:-1]
                else:
                    value = value.split(" #", 1)[0].strip()
                os.environ["CORE_API_KEY"] = value
                break
    key = os.environ.get("CORE_API_KEY", "").strip()
    if not key:
        raise SeedError("CORE_API_KEY is missing; set it in the root .env or environment.")
    return key


class CoreApi:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def call(self, method: str, path: str, body: object | None = None) -> Any:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json", "X-API-Key": self.api_key},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise ApiError(exc.code, method, path) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            raise SeedError("core-api is not running; start scripts\\dev-up.ps1 first.") from None
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise SeedError(f"core-api returned invalid JSON for {method} {path}.") from None


def local_now() -> datetime:
    return datetime.now(LOCAL_TZ).replace(tzinfo=None)


def parse_local_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        return parsed.astimezone(LOCAL_TZ).replace(tzinfo=None)
    return parsed


def appointment_dates(today: date) -> list[date]:
    return [
        day
        for offset in range(42)
        if (day := today + timedelta(days=offset)).weekday() in (1, 4)
    ]


def get_user(api: CoreApi) -> dict[str, Any] | None:
    try:
        return api.call("GET", f"/users/{USER_ID}")
    except ApiError as exc:
        if exc.status == 404:
            return None
        raise


def get_seed_rows(api: CoreApi) -> dict[str, list[dict[str, Any]]]:
    return {
        "contacts": api.call("GET", f"/users/{USER_ID}/contacts"),
        "medicines": api.call("GET", f"/users/{USER_ID}/medicines"),
        "appointments": api.call("GET", f"/users/{USER_ID}/appointments"),
        "reminders": api.call("GET", f"/users/{USER_ID}/reminders"),
    }


def add_action(
    actions: list[dict[str, Any]],
    resource: str,
    operation: str,
    detail: str,
    method: str | None = None,
    path: str | None = None,
    body: dict[str, Any] | None = None,
) -> None:
    actions.append(
        {
            "resource": resource,
            "operation": operation,
            "detail": detail,
            "method": method,
            "path": path,
            "body": body,
        }
    )


def plan_seed(
    current: dict[str, Any],
    rows: dict[str, list[dict[str, Any]]],
    now: datetime,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    profile_changes = {key: value for key, value in USER_PROFILE.items() if current.get(key) != value}
    if profile_changes:
        add_action(
            actions,
            "User profile",
            "update",
            json.dumps(profile_changes, ensure_ascii=False, sort_keys=True),
            "PATCH",
            f"/users/{USER_ID}",
            profile_changes,
        )
    else:
        add_action(actions, "User profile", "correct", "All requested profile fields match.")

    contact = next((row for row in rows["contacts"] if row.get("name") == CONTACT["name"]), None)
    if contact is None:
        add_action(
            actions,
            "Contact",
            "create",
            f"{CONTACT['name']} ({CONTACT['relation']}, synthetic number)",
            "POST",
            f"/users/{USER_ID}/contacts",
            CONTACT,
        )
    else:
        add_action(actions, "Contact", "present", f"{CONTACT['name']} already exists; left unchanged.")

    for target in MEDICINES:
        found = next((row for row in rows["medicines"] if row.get("name") == target["name"]), None)
        if found is None:
            add_action(
                actions,
                f"Medicine: {target['name']}",
                "create",
                json.dumps(target, ensure_ascii=False, sort_keys=True),
                "POST",
                f"/users/{USER_ID}/medicines",
                target,
            )
            continue
        changes = {key: value for key, value in target.items() if found.get(key) != value}
        if changes:
            add_action(
                actions,
                f"Medicine: {target['name']}",
                "update",
                json.dumps(changes, ensure_ascii=False, sort_keys=True),
                "PATCH",
                f"/users/{USER_ID}/medicines/{found['id']}",
                changes,
            )
        else:
            add_action(actions, f"Medicine: {target['name']}", "correct", "All requested fields match.")

    for day in appointment_dates(now.date()):
        starts_at = datetime.combine(day, time(18, 0))
        if any(
            row.get("title") == "गायन वर्ग"
            and parse_local_datetime(row["starts_at"]) == starts_at
            for row in rows["appointments"]
        ):
            add_action(
                actions,
                "Singing class",
                "present",
                f"{day.isoformat()} 18:00 already exists.",
            )
            continue
        payload = {
            "title": "गायन वर्ग",
            "starts_at": starts_at.isoformat(),
            "location": "गायन वर्ग",
        }
        add_action(
            actions,
            "Singing class",
            "create",
            f"{day.isoformat()} 18:00 at गायन वर्ग",
            "POST",
            f"/users/{USER_ID}/appointments",
            payload,
        )

    for task, at in REMINDERS:
        for day in (now.date(), now.date() + timedelta(days=1)):
            due_at = datetime.combine(day, time.fromisoformat(at))
            label = f"{task} — {day.isoformat()} {at}"
            if due_at <= now:
                add_action(actions, "Reminder", "skip", f"{label} is not in the future.")
                continue
            exists = any(
                row.get("task") == task and parse_local_datetime(row["due_at"]) == due_at
                for row in rows["reminders"]
            )
            if exists:
                add_action(actions, "Reminder", "present", f"{label} already exists.")
                continue
            add_action(
                actions,
                "Reminder",
                "create",
                label,
                "POST",
                f"/users/{USER_ID}/reminders",
                {"task": task, "date": day.isoformat(), "time": at},
            )
    return actions


def display_plan(actions: list[dict[str, Any]], apply: bool) -> None:
    print("Planned changes:")
    for action in actions:
        operation = action["operation"]
        if operation == "create":
            verb = "CREATE" if apply else "WOULD CREATE"
        elif operation == "update":
            verb = "UPDATE" if apply else "WOULD UPDATE"
        elif operation == "skip":
            verb = "SKIP"
        elif operation == "blocked":
            verb = "BLOCKED"
        elif operation == "present":
            verb = "ALREADY PRESENT"
        else:
            verb = "ALREADY CORRECT"
        print(f"  {verb:16} {action['resource']}: {action['detail']}")


def print_summary(results: list[tuple[str, str, str]]) -> None:
    print("\nSummary:")
    print(f"  {'Resource':24} | {'Result':18} | Detail")
    print(f"  {'-' * 24}-+-{'-' * 18}-+-{'-' * 52}")
    for resource, result, detail in results:
        print(f"  {resource:24} | {result:18} | {detail}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Seed the synthetic Heerabai demo user.")
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    parser.add_argument("--core", default="http://127.0.0.1:8000", help="core-api base URL")
    args = parser.parse_args()
    if not args.core.startswith(("http://", "https://")) or "@" in args.core.split("://", 1)[-1].split("/", 1)[0]:
        parser.error("--core must be an http(s) URL without embedded credentials.")

    try:
        api = CoreApi(args.core, load_api_key())
        now = local_now()
        user = get_user(api)
        user_missing = user is None
        created_user = False

        if user_missing and args.apply:
            print(f"Creating user {USER_ID} through core-api.")
            user = api.call("POST", "/users", {"name": USER_NAME})
            if user.get("id") != USER_ID:
                raise SeedError(
                    f"core-api assigned user id {user.get('id')} instead of {USER_ID}; "
                    "the requested user was not seeded."
                )
            created_user = True
        elif user is None:
            user = {
                "name": USER_NAME,
                "language": "mr",
                "wake_time": "07:00",
                "lunch_time": "13:00",
                "dinner_time": "20:00",
                "interests": [],
                "opener_start": "10:00",
                "opener_end": "18:00",
                "consent_distress_alert": False,
            }

        rows = (
            {key: [] for key in ("contacts", "medicines", "appointments", "reminders")}
            if user_missing and not args.apply
            else get_seed_rows(api)
        )
        actions = plan_seed(user, rows, now)
        if user is None:
            raise SeedError(f"Could not load user {USER_ID}.")

        user_create_action = None
        if not created_user and user.get("id") is None and not args.apply:
            user_create_action = {
                "resource": "User",
                "operation": "create",
                "detail": f"user {USER_ID}: {USER_NAME}",
                "method": "POST",
                "path": "/users",
                "body": {"name": USER_NAME},
            }
        if created_user:
            results = [("User", "created", f"user {USER_ID}: {USER_NAME}")]
        else:
            results = []
        if not user_missing and user.get("name") != USER_NAME:
            actions.insert(
                0,
                {
                    "resource": "User name",
                    "operation": "blocked",
                    "detail": (
                        f"Cannot set the requested name: PATCH /users/{USER_ID} does not accept name."
                    ),
                    "method": None,
                    "path": None,
                    "body": None,
                },
            )
        if user_create_action is not None:
            actions.insert(0, user_create_action)
        display_plan(actions, args.apply)

        for action in actions:
            operation = action["operation"]
            if operation == "blocked":
                results.append(("User name", "blocked", action["detail"]))
                continue
            if operation in ("present", "correct", "skip"):
                result = "already correct" if operation == "correct" else (
                    "skipped" if operation == "skip" else "already present"
                )
                results.append((action["resource"], result, action["detail"]))
                continue
            if operation == "create" and action is user_create_action:
                results.append(("User", "would create", action["detail"]))
                continue
            if not args.apply:
                results.append(
                    (
                        action["resource"],
                        f"would {operation}",
                        action["detail"],
                    )
                )
                continue
            api.call(action["method"], action["path"], action["body"])
            result = "created" if operation == "create" else "updated"
            results.append((action["resource"], result, action["detail"]))

        if not created_user and not user_missing and user.get("name") == USER_NAME:
            results.insert(0, ("User", "already correct", f"user {USER_ID}: {USER_NAME}"))
        print_summary(results)
        if not args.apply:
            print("\nDry run only; nothing was written.")
        return 1 if any(result == "blocked" for _, result, _ in results) else 0
    except SeedError as exc:
        print(f"seed_heerabai: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
