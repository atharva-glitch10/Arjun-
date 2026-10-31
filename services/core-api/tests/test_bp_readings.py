"""BP readings are stored exactly as the elder says them: raw numbers, no judgement, no advice.

Boundary 7: Arjun never says a reading is good, bad, high, low or normal; it repeats the numbers back and
shows the raw values to the family.
"""


def test_a_reading_is_stored_raw_and_listed(client, uid):
    r = client.post(f"/users/{uid}/bp-readings", json={"systolic": 132, "diastolic": 86})
    assert r.status_code == 201, r.text
    row = r.json()
    assert (row["systolic"], row["diastolic"], row["pulse"]) == (132, 86, None)
    assert row["source"] == "voice" and row["measured_at"]

    rows = client.get(f"/users/{uid}/bp-readings").json()
    assert [(x["systolic"], x["diastolic"]) for x in rows] == [(132, 86)]
    # No judgement is stored or returned.
    assert not any(k in row for k in ("status", "level", "judgement", "advice"))


def test_a_pulse_can_be_recorded_and_values_are_validated(client, uid):
    ok = client.post(f"/users/{uid}/bp-readings", json={"systolic": 120, "diastolic": 80, "pulse": 72})
    assert ok.status_code == 201 and ok.json()["pulse"] == 72
    assert client.post(f"/users/{uid}/bp-readings", json={"systolic": 0, "diastolic": 80}).status_code == 422
    assert client.post(f"/users/{uid}/bp-readings", json={"systolic": 120}).status_code == 422


def test_readings_belong_to_one_family(client, uid):
    other = client.post("/users", json={"name": "Other (synthetic)"}).json()["id"]
    assert client.post(f"/users/{other}/bp-readings", json={"systolic": 118, "diastolic": 76}).status_code == 201
    assert client.get(f"/users/{uid}/bp-readings").json() == []
    assert len(client.get(f"/users/{other}/bp-readings").json()) == 1


def test_measured_at_is_the_household_clock(client, uid):
    row = client.post(f"/users/{uid}/bp-readings", json={"systolic": 132, "diastolic": 86}).json()
    assert row["measured_at"] == "2026-10-06T09:00:00"
