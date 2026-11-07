def test_sound_events_keep_only_label_confidence_and_return_daily_cough_trend(client, uid):
    cough = client.post(f"/users/{uid}/sound-events", json={"label": "cough", "confidence": 0.82})
    bang = client.post(f"/users/{uid}/sound-events", json={"label": "bang", "confidence": 0.91})
    assert cough.status_code == 201 and cough.json() == {"recorded": True, "label": "cough", "confidence": 0.82}
    assert bang.status_code == 201 and bang.json()["label"] == "bang"
    trend = client.get(f"/users/{uid}/sound-events?days=3").json()
    assert trend["total_coughs"] == 1
    assert len(trend["days"]) == 3
    assert sum(day["cough_count"] for day in trend["days"]) == 1
    assert "audio" not in cough.json()


def test_sound_events_validate_label_and_confidence(client, uid):
    assert client.post(f"/users/{uid}/sound-events", json={"label": "voice", "confidence": 0.9}).status_code == 422
    assert client.post(f"/users/{uid}/sound-events", json={"label": "cough", "confidence": 1.2}).status_code == 422


def test_sound_event_no_answer_uses_existing_emergency_flow(client, uid, monkeypatch):
    from core_api import main

    called = []
    monkeypatch.setattr(main, "record_distress", lambda user_id, kind, db, now: called.append((user_id, kind)) or type("Result", (), {"caregiver_alerted": True})())
    result = client.post(f"/users/{uid}/sound-events/escalate")
    assert result.status_code == 200 and result.json() == {"alerted": True}
    assert called == [(uid, "emergency")]
