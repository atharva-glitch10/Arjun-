"""A synthetic watch feed: raw samples only, clearly labelled synthetic.

No device is paired. A small simulator (or the seed) posts steps, heart rate and sleep; the family sees the
raw numbers with a timestamp. Nothing is scored, compared to a target, or turned into an alert.
"""


def test_watch_samples_are_stored_raw_and_listed_newest_first(client, uid):
    first = client.post(f"/users/{uid}/watch-samples", json={"kind": "steps", "value": 2100})
    assert first.status_code == 201, first.text
    assert first.json()["unit"] == "steps" and first.json()["source"] == "synthetic-watch"
    second = client.post(f"/users/{uid}/watch-samples", json={"kind": "heart_rate", "value": 74})
    assert second.status_code == 201 and second.json()["unit"] == "bpm"

    rows = client.get(f"/users/{uid}/watch-samples").json()
    assert [(x["kind"], x["value"]) for x in rows] == [("heart_rate", 74), ("steps", 2100)]
    assert not any(k in rows[0] for k in ("status", "level", "target", "advice"))


def test_watch_samples_can_be_filtered_by_kind_and_latest(client, uid):
    client.post(f"/users/{uid}/watch-samples", json={"kind": "steps", "value": 1200})
    client.post(f"/users/{uid}/watch-samples", json={"kind": "steps", "value": 3400})
    client.post(f"/users/{uid}/watch-samples", json={"kind": "sleep_minutes", "value": 410})
    steps = client.get(f"/users/{uid}/watch-samples?kind=steps").json()
    assert [x["value"] for x in steps] == [3400, 1200]
    latest = client.get(f"/users/{uid}/watch-samples/latest").json()
    assert {x["kind"]: x["value"] for x in latest} == {"steps": 3400, "sleep_minutes": 410}


def test_an_unknown_sample_kind_is_rejected(client, uid):
    assert client.post(f"/users/{uid}/watch-samples", json={"kind": "blood_sugar", "value": 90}).status_code == 422
    assert client.post(f"/users/{uid}/watch-samples", json={"kind": "steps", "value": -1}).status_code == 422


def test_watch_samples_belong_to_one_family(client, uid):
    other = client.post("/users", json={"name": "Other (synthetic)"}).json()["id"]
    client.post(f"/users/{other}/watch-samples", json={"kind": "steps", "value": 900})
    assert client.get(f"/users/{uid}/watch-samples").json() == []
