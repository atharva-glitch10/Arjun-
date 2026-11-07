from fastapi.testclient import TestClient
from reasoning_svc import main


def test_sound_event_sends_only_label_and_confidence_to_core(core_http, engine, uid, monkeypatch):
    monkeypatch.setattr(main, "_engine", engine)
    with TestClient(main.app) as client:
        response = client.post("/sound-event", json={"user_id": uid, "label": "cough", "confidence": 0.88})
    assert response.status_code == 200 and response.json() == {"recorded": True}
    trend = core_http.get(f"/users/{uid}/sound-events?days=1").json()
    assert trend["total_coughs"] == 1


def test_sound_event_unanswered_escalates_via_existing_emergency_endpoint(core_http, engine, uid, monkeypatch):
    monkeypatch.setattr(main, "_engine", engine)
    with TestClient(main.app) as client:
        response = client.post("/sound-event/escalate", json={"user_id": uid})
    assert response.status_code == 200 and response.json() == {"alerted": True}
    alerts = core_http.get(f"/users/{uid}/notifications").json()
    assert any(item["kind"] == "emergency" for item in alerts)
