"""Task B: a weekly appointment (a singing class, Tuesday and Friday 18:00-19:00).

`starts_at` stays the first day the rule applies; the occurrence on any later matching weekday comes from
weekdays + start_time. The day view and "next appointment" both use the occurrence, never the raw row.
"""

from datetime import datetime

from core_api.main import app, get_now

MONDAY = datetime(2026, 10, 5, 9, 0)  # 2026-10-05 is a Monday


def set_now(value: datetime) -> None:
    app.dependency_overrides[get_now] = lambda: value


def _class(client, uid) -> int:
    r = client.post(
        f"/users/{uid}/appointments",
        json={
            "title": "गायन वर्ग", "starts_at": "2026-10-05T18:00:00", "location": "गायन वर्ग",
            "weekdays": [1, 4], "start_time": "18:00", "end_time": "19:00",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_a_weekly_appointment_needs_a_start_time_and_valid_weekdays(client, uid):
    body = {"title": "गायन वर्ग", "starts_at": "2026-10-05T18:00:00", "weekdays": [1, 4]}
    assert client.post(f"/users/{uid}/appointments", json=body).status_code == 422
    body["start_time"] = "18:00"
    body["weekdays"] = [7]
    assert client.post(f"/users/{uid}/appointments", json=body).status_code == 422
    body["weekdays"] = []
    assert client.post(f"/users/{uid}/appointments", json=body).status_code == 422


def test_a_weekly_appointment_appears_only_on_its_weekdays(client, uid):
    set_now(MONDAY)
    _class(client, uid)
    monday = client.get(f"/users/{uid}/day", params={"on": "2026-10-05"}).json()["items"]
    tuesday = client.get(f"/users/{uid}/day", params={"on": "2026-10-06"}).json()["items"]
    friday = client.get(f"/users/{uid}/day", params={"on": "2026-10-09"}).json()["items"]
    saturday = client.get(f"/users/{uid}/day", params={"on": "2026-10-10"}).json()["items"]
    assert [i["label"] for i in monday if i["kind"] == "appointment"] == []
    assert [(i["label"], i["at"][11:16]) for i in tuesday if i["kind"] == "appointment"] == [("गायन वर्ग", "18:00")]
    assert [(i["label"], i["at"][11:16]) for i in friday if i["kind"] == "appointment"] == [("गायन वर्ग", "18:00")]
    assert [i["label"] for i in saturday if i["kind"] == "appointment"] == []


def test_the_rule_starts_on_the_first_day_it_applies(client, uid):
    set_now(MONDAY)
    client.post(
        f"/users/{uid}/appointments",
        json={
            "title": "गायन वर्ग", "starts_at": "2026-10-07T18:00:00", "weekdays": [1, 4], "start_time": "18:00",
        },
    )
    # Tuesday 6 Oct comes BEFORE the rule's first day (Wednesday 7 Oct): nothing.
    before = client.get(f"/users/{uid}/day", params={"on": "2026-10-06"}).json()["items"]
    after = client.get(f"/users/{uid}/day", params={"on": "2026-10-09"}).json()["items"]
    assert [i["label"] for i in before if i["kind"] == "appointment"] == []
    assert [i["label"] for i in after if i["kind"] == "appointment"] == ["गायन वर्ग"]


def test_next_appointment_on_monday_is_tuesdays_class(client, uid):
    set_now(MONDAY)
    _class(client, uid)
    a = client.get(f"/users/{uid}/appointments/next").json()
    assert a["title"] == "गायन वर्ग" and a["starts_at"] == "2026-10-06T18:00:00"


def test_next_appointment_after_tuesdays_class_is_fridays(client, uid):
    set_now(datetime(2026, 10, 6, 19, 30))  # Tuesday, class over
    _class(client, uid)
    a = client.get(f"/users/{uid}/appointments/next").json()
    assert a["starts_at"] == "2026-10-09T18:00:00"


def test_one_off_appointment_behaviour_is_unchanged(client, uid):
    set_now(MONDAY)
    client.post(
        f"/users/{uid}/appointments", json={"title": "Eye check", "starts_at": "2026-10-06T11:00:00", "location": "Pune"}
    )
    nxt = client.get(f"/users/{uid}/appointments/next").json()
    assert nxt["starts_at"] == "2026-10-06T11:00:00" and nxt["weekdays"] is None
    items = client.get(f"/users/{uid}/day", params={"on": "2026-10-07"}).json()["items"]
    assert [i["label"] for i in items if i["kind"] == "appointment"] == []
