"""The family call link: a short-lived signed token opens the elder's current LiveKit room."""

import pytest
from core_api import joins
from core_api.livekit_token import reset_rooms_for_tests


@pytest.fixture(autouse=True)
def _clean_rooms():
    reset_rooms_for_tests()
    yield
    reset_rooms_for_tests()


@pytest.fixture()
def livekit(monkeypatch):
    monkeypatch.setenv("LIVEKIT_URL", "wss://example.test")
    monkeypatch.setenv("LIVEKIT_API_KEY", "lk-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "lk-secret")
    monkeypatch.setenv("JOIN_SECRET", "join-secret")


def _open_room(client, uid: int) -> str:
    res = client.post("/livekit/token", json={"user_id": uid})
    assert res.status_code == 200
    return res.json()["room"]


def test_a_valid_link_returns_a_family_token_for_the_elder_room(client, uid, livekit):
    room = _open_room(client, uid)
    res = client.get("/family/join", params={"t": joins.issue(uid)})
    assert res.status_code == 200
    data = res.json()
    assert data["room"] == room
    assert data["identity"] == "family"
    assert data["url"] == "wss://example.test"
    assert data["expires_in"] > 0
    assert data["token"]


def test_the_link_follows_the_elder_to_a_newer_room(client, uid, livekit):
    first = _open_room(client, uid)
    link = joins.issue(uid)  # the alert was sent while the first room was open
    second = _open_room(client, uid)  # the elder closed the app and opened it again
    assert second != first
    data = client.get("/family/join", params={"t": link}).json()
    assert data["room"] == second


def test_an_expired_link_is_rejected(client, uid, livekit):
    _open_room(client, uid)
    token = joins.issue(uid, now=1_000.0)  # issued long ago
    assert client.get("/family/join", params={"t": token}).status_code == 403


def test_a_forged_link_is_rejected(client, uid, livekit):
    _open_room(client, uid)
    good = joins.issue(uid)
    uid_s, exp_s, _sig = good.split(".")
    forged = f"{uid_s}.{int(exp_s) + 3600}.AAAA"
    assert client.get("/family/join", params={"t": forged}).status_code == 403
    assert client.get("/family/join", params={"t": "not-a-link"}).status_code == 403


def test_a_link_for_a_missing_user_is_not_found(client, uid, livekit):
    _open_room(client, uid)
    assert client.get("/family/join", params={"t": joins.issue(999)}).status_code == 404


def test_without_an_open_room_the_link_is_a_conflict(client, uid, livekit):
    assert client.get("/family/join", params={"t": joins.issue(uid)}).status_code == 409


def test_the_family_name_is_the_son_never_the_doctor(client, uid, livekit):
    _open_room(client, uid)
    client.post(
        f"/users/{uid}/contacts",
        json={"name": "डॉ. कुलकर्णी", "relation": "डॉक्टर", "phone": "00000 00001"},
    )
    client.post(
        f"/users/{uid}/contacts",
        json={"name": "चंद्रकांत", "relation": "मुलगा", "phone": "00000 00002"},
    )
    data = client.get("/family/join", params={"t": joins.issue(uid)}).json()
    assert data["name"] == "चंद्रकांत"


def test_a_doctor_only_contact_list_falls_back_to_family(client, uid, livekit):
    _open_room(client, uid)
    client.post(
        f"/users/{uid}/contacts",
        json={"name": "डॉ. कुलकर्णी", "relation": "डॉक्टर", "phone": "00000 00001"},
    )
    data = client.get("/family/join", params={"t": joins.issue(uid)}).json()
    assert data["name"] == "कुटुंब"


def test_join_url_points_at_the_web_join_view(client, uid, livekit, monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://arjun.example.test/")
    url = joins.join_url(uid)
    assert url.startswith("https://arjun.example.test/?view=join&t=")
    token = url.split("t=", 1)[1]
    assert joins.verify(token) == uid


def test_call_bound_join_links_keep_the_call_id_signed(client, uid, monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://arjun.example.test")
    token = joins.issue(uid, call_id=37)
    assert joins.claims(token) == (uid, 37)
    assert joins.verify(token) == uid
    assert "37." in token
