from datetime import datetime, timedelta

from core_api.deps import local_now
from core_api.main import app, get_now

NOW = datetime(2026, 10, 6, 9, 0)


def test_day_view_orders_sql_items_and_finds_next(client, uid):
    client.patch(f"/users/{uid}", json={"lunch_time": "13:00", "dinner_time": "20:00"})
    client.post(
        f"/users/{uid}/reminders", json={"task": "call Rahul", "date": "2026-10-06", "time": "16:00"}
    )
    client.post(
        f"/users/{uid}/appointments",
        json={"title": "Eye check", "starts_at": "2026-10-06T11:00:00", "location": "Pune"},
    )
    d = client.get(f"/users/{uid}/day").json()
    assert d["now"].startswith("2026-10-06T09:00") and d["part"] == "morning" and d["weekday"] == 1
    labels = [(i["kind"], i["label"]) for i in d["items"]]
    assert labels == [
        ("wake", "wake"),
        ("appointment", "Eye check"),
        ("meal", "lunch"),
        ("reminder", "call Rahul"),
        ("meal", "dinner"),
    ]
    assert d["next"]["label"] == "Eye check" and d["next"]["detail"] == "Pune"
    assert d["open_now"] == []  # wake time passed, but it is not a task


def test_day_view_open_now_lists_due_medicine_and_unfinished_reminder(client, uid):
    box = {"now": NOW - timedelta(hours=3)}
    app.dependency_overrides[get_now] = lambda: box["now"]
    client.post(
        f"/users/{uid}/medicines",
        json={"name": "Telma AM", "dose": "[dose]", "anchor": "fixed", "time": "09:00"},
    )
    client.post(
        f"/users/{uid}/reminders", json={"task": "water plants", "date": "2026-10-06", "time": "08:30"}
    )
    box["now"] = NOW
    d = client.get(f"/users/{uid}/day").json()
    assert [(i["kind"], i["label"]) for i in d["open_now"]] == [
        ("reminder", "water plants"),
        ("medicine", "Telma AM"),
    ]
    dose_id = d["open_now"][1]["ref_id"]
    client.post(f"/users/{uid}/medicine-doses/{dose_id}/taken")
    assert [i["kind"] for i in client.get(f"/users/{uid}/day").json()["open_now"]] == ["reminder"]


def test_day_unknown_user_404(client):
    assert client.get("/users/999/day").status_code == 404


def test_clock_uses_household_timezone_not_machine_timezone(monkeypatch):
    monkeypatch.setenv("ARJUN_TZ", "Asia/Kolkata")
    ist = local_now()
    monkeypatch.setenv("ARJUN_TZ", "UTC")
    utc = local_now()
    assert abs((ist - utc).total_seconds() - 5.5 * 3600) < 5
