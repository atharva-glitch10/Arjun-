from datetime import timedelta

from core_api import joins, video_calls
from core_api.deps import local_now
from core_api.livekit_token import remember_room, reset_rooms_for_tests


def setup_function():
    reset_rooms_for_tests()


def _room(client, uid):
    remember_room(uid, "elder-room-test")


def _contact(client, uid, name="चंद्रकांत", relation="मुलगा"):
    return client.post(f"/users/{uid}/contacts", json={"name": name, "relation": relation, "phone": "00000 00001"}).json()


def test_start_sends_video_ring_once_and_dedupes(client, uid, monkeypatch):
    _room(client, uid)
    contact = _contact(client, uid)
    monkeypatch.setenv("BASE_URL", "https://arjun.example.test")
    sent = []
    monkeypatch.setattr(video_calls.telegram, "send_alert", lambda *a, **kw: sent.append((a, kw)) or True)
    first = client.post(f"/users/{uid}/calls", json={"contact_id": contact["id"], "mode": "video"})
    second = client.post(f"/users/{uid}/calls", json={"contact_id": contact["id"], "mode": "video"})
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["status"] == second.json()["status"] == "ringing"
    assert first.json()["id"] == second.json()["id"]
    assert len(sent) == 1
    assert sent[0][0][0] == "📹 Aaji व्हिडिओ कॉल करत आहेत"
    assert sent[0][1]["button_text"] == "उचला"
    assert "/?view=join&t=" in sent[0][0][1]


def test_doctors_cannot_be_called(client, uid):
    _room(client, uid)
    doctor = _contact(client, uid, "डॉ. कुलकर्णी", "डॉक्टर")
    assert client.post(f"/users/{uid}/calls", json={"contact_id": doctor["id"], "mode": "video"}).status_code == 422


def test_family_join_marks_answered_only_after_livekit_connects(client, uid, monkeypatch):
    _room(client, uid)
    contact = _contact(client, uid)
    monkeypatch.setenv("LIVEKIT_URL", "wss://example.test")
    monkeypatch.setenv("LIVEKIT_API_KEY", "lk-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "lk-secret")
    monkeypatch.setenv("JOIN_SECRET", "join-secret")
    from core_api.deps import local_now
    from core_api.main import app, get_now
    app.dependency_overrides[get_now] = lambda: local_now()
    call = client.post(f"/users/{uid}/calls", json={"contact_id": contact["id"]}).json()
    link = joins.issue(uid, call_id=call["id"])
    result = client.get("/family/join", params={"t": link}).json()
    assert result["mode"] == "video" and result["call_id"] == call["id"]
    assert client.get(f"/users/{uid}/calls/{call['id']}").json()["status"] == "ringing"
    assert client.post("/family/calls/answer", json={"t": link}).json()["status"] == "answered"
    assert client.get(f"/users/{uid}/calls/{call['id']}").json()["status"] == "answered"
    assert client.get("/family/join", params={"t": link}).json()["mode"] == "video"
    assert client.post(f"/users/{uid}/calls/{call['id']}/end").json()["status"] == "ended"
    assert client.get("/family/join", params={"t": link}).status_code == 410


def test_ringing_call_times_out_and_notifies_feed(client, uid, monkeypatch):
    _room(client, uid)
    contact = _contact(client, uid)
    monkeypatch.setenv("BASE_URL", "https://arjun.example.test")
    sent = []
    monkeypatch.setattr(video_calls.telegram, "send_alert", lambda *a, **kw: sent.append((a, kw)) or True)
    call = client.post(f"/users/{uid}/calls", json={"contact_id": contact["id"]}).json()
    old = client.get(f"/users/{uid}/calls/{call['id']}")
    assert old.json()["status"] == "ringing"
    from core_api.main import app, get_now
    app.dependency_overrides[get_now] = lambda: local_now() + timedelta(seconds=61)
    try:
        missed = client.get(f"/users/{uid}/calls/{call['id']}")
    finally:
        app.dependency_overrides[get_now] = lambda: local_now()
    assert missed.json()["status"] == "missed"
    assert sent[-1][0][0].endswith("व्हिडिओ कॉल चुकला — परत करा")
    assert sent[-1][1]["button_text"] == "परत करा"
    assert any(row["kind"] == "video_call_missed" for row in client.get(f"/users/{uid}/notifications").json())
