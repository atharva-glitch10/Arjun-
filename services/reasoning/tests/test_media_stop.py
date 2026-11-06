from fastapi.testclient import TestClient
from reasoning_svc import main


def test_media_stopped_endpoint_clears_pending_media_state_and_notes_history(monkeypatch):
    class Engine:
        def __init__(self):
            self.calls = []

        def media_stopped(self, user_id):
            self.calls.append(user_id)

    engine = Engine()
    monkeypatch.setattr(main, "_engine", engine)
    with TestClient(main.app) as client:
        response = client.post("/media/stopped", json={"user_id": 42})
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert engine.calls == [42]


def test_engine_media_stop_clears_choice_and_followup_and_records_one_note(engine):
    events = []
    engine._media_choice[7] = object()
    engine._media_ask[7] = 123.0
    engine.memory.event = lambda uid, now, text: events.append((uid, text))
    engine.media_stopped(7)
    assert 7 not in engine._media_choice
    assert 7 not in engine._media_ask
    assert events == [(7, "[media stopped]")]
