def _uid(client):
    return client.post("/users", json={"name": "Test Aaji"}).json()["id"]


def test_profile_empty_then_saved_and_cleaned(client):
    uid = _uid(client)
    assert client.get(f"/users/{uid}/health-profile").json()["allergies"] == []
    r = client.put(
        f"/users/{uid}/health-profile",
        json={"allergies": ["Penicillin", " penicillin ", "Peanuts", ""], "conditions": ["BP"], "blood_group": "O+",
              "doctor_name": "Dr Test", "prescription_notes": "Review in 3 months"},
    )
    assert r.status_code == 200
    got = client.get(f"/users/{uid}/health-profile").json()
    assert got["allergies"] == ["Penicillin", "Peanuts"]  # blanks and case-duplicates dropped
    assert got["conditions"] == ["BP"] and got["blood_group"] == "O+" and got["doctor_name"] == "Dr Test"
    assert client.get(f"/users/{uid}").json()["conditions"] == ["BP"]


def test_profile_unknown_user_404(client):
    assert client.get("/users/9999/health-profile").status_code == 404


def test_medicine_keeps_prescription_fields_verbatim(client):
    uid = _uid(client)
    r = client.post(
        f"/users/{uid}/medicines",
        json={"name": "Telma 40", "dose": "1 tablet", "anchor": "fixed", "time": "09:00",
              "prescribed_by": "Dr Test", "instructions": "After breakfast"},
    )
    assert r.status_code == 201
    assert r.json()["prescribed_by"] == "Dr Test" and r.json()["instructions"] == "After breakfast"
    mid = r.json()["id"]
    r = client.patch(f"/users/{uid}/medicines/{mid}", json={"instructions": "With water"})
    assert r.json()["instructions"] == "With water" and r.json()["prescribed_by"] == "Dr Test"


def test_medicine_check_reports_self_reported_timing(client):
    uid = _uid(client)
    client.post(f"/users/{uid}/medicines", json={"name": "Telma 40", "dose": "1 tablet", "anchor": "fixed", "time": "09:00", "window_min": 30})
    client.post("/internal/medicines/tick")
    rows = client.get(f"/users/{uid}/medicine-check").json()
    assert len(rows) == 1
    assert rows[0]["name"] == "Telma 40" and rows[0]["self_reported"] is True
    assert rows[0]["timing"] == "pending" and rows[0]["taken_at"] is None  # due now, nothing reported yet
    did = rows[0]["dose_id"]
    assert client.post(f"/users/{uid}/medicine-doses/{did}/taken").status_code == 200
    row = client.get(f"/users/{uid}/medicine-check").json()[0]
    assert row["status"] == "taken" and row["timing"] == "on_time" and row["minutes_late"] == 0
