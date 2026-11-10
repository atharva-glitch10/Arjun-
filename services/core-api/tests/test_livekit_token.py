"""POST /livekit/token: the elder app's only way into a voice room (T6)."""

import base64
import json
import re
import time

import pytest
from livekit import api as lk

SECRET = "s3cr3t-" + "x" * 33
KEY = "APItestkey"


@pytest.fixture()
def lk_env(monkeypatch):
    monkeypatch.setenv("LIVEKIT_URL", "wss://example.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_API_KEY", KEY)
    monkeypatch.setenv("LIVEKIT_API_SECRET", SECRET)
    monkeypatch.setenv("ARJUN_AGENT_NAME", "arjun")


def _payload(token: str) -> dict:
    p = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))


def test_token_joins_a_fresh_room_and_dispatches_arjun(client, uid, lk_env):
    r = client.post("/livekit/token", json={"user_id": uid})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"url", "token", "room", "identity", "expires_in"}
    assert body["url"] == "wss://example.livekit.cloud" and body["identity"] == f"elder-{uid}"
    assert re.fullmatch(rf"elder-{uid}-\d{{14}}-[0-9a-f]{{6}}", body["room"])
    lk.TokenVerifier(KEY, SECRET).verify(body["token"])  # signed with the server secret, not expired
    claims = _payload(body["token"])
    video = claims["video"]
    assert video["room"] == body["room"] and video["roomJoin"] is True
    assert video["canPublish"] is True and video["canSubscribe"] is True
    assert video["canPublishSources"] == ["microphone", "camera"]  # video calls start only after the elder asks
    assert not video.get("roomAdmin") and not video.get("canUpdateOwnMetadata")
    agents = claims["roomConfig"]["agents"]
    assert [a["agentName"] for a in agents] == ["arjun"]  # explicit dispatch
    assert json.loads(agents[0]["metadata"]) == {"user_id": uid}  # the agent serves THIS user, not an env default
    assert claims["sub"] == f"elder-{uid}"


def test_token_is_short_lived(client, uid, lk_env):
    body = client.post("/livekit/token", json={"user_id": uid}).json()
    ttl = _payload(body["token"])["exp"] - int(time.time())
    assert 0 < ttl <= 600 and body["expires_in"] == 600


def test_every_call_gets_its_own_room(client, uid, lk_env):
    rooms = {client.post("/livekit/token", json={"user_id": uid}).json()["room"] for _ in range(3)}
    assert len(rooms) == 3  # dispatch only happens when a room is created


def test_secret_never_appears_in_the_response(client, uid, lk_env):
    r = client.post("/livekit/token", json={"user_id": uid})
    assert SECRET not in r.text and SECRET not in json.dumps(_payload(r.json()["token"]))


def test_agent_name_defaults_to_arjun(client, uid, lk_env, monkeypatch):
    monkeypatch.delenv("ARJUN_AGENT_NAME")
    body = client.post("/livekit/token", json={"user_id": uid}).json()
    assert [a["agentName"] for a in _payload(body["token"])["roomConfig"]["agents"]] == ["arjun"]


def test_same_auth_as_the_other_routes(client, uid, lk_env, monkeypatch):
    monkeypatch.setenv("CORE_API_KEY", "k" * 24)
    assert client.post("/livekit/token", json={"user_id": uid}).status_code == 401
    ok = client.post("/livekit/token", json={"user_id": uid}, headers={"X-API-Key": "k" * 24})
    assert ok.status_code == 200


@pytest.mark.parametrize("missing", ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"])
def test_unconfigured_livekit_is_a_503_that_names_nothing(client, uid, lk_env, monkeypatch, missing):
    monkeypatch.delenv(missing)
    r = client.post("/livekit/token", json={"user_id": uid})
    assert r.status_code == 503
    assert "LIVEKIT" not in r.text and SECRET not in r.text


def test_unknown_user_is_404(client, lk_env):
    assert client.post("/livekit/token", json={"user_id": 999}).status_code == 404


def test_the_screen_language_rides_in_the_dispatch_metadata(client, uid, lk_env):
    """The frontend owns the language (2026-11-10): the token body's `language` reaches the agent in the dispatch metadata."""
    r = client.post("/livekit/token", json={"user_id": uid, "language": "hi"})
    assert r.status_code == 200
    meta = json.loads(_payload(r.json()["token"])["roomConfig"]["agents"][0]["metadata"])
    assert meta == {"user_id": uid, "language": "hi"}


def test_a_token_without_a_language_is_unchanged_and_a_bad_language_is_refused(client, uid, lk_env):
    meta = json.loads(_payload(client.post("/livekit/token", json={"user_id": uid}).json()["token"])["roomConfig"]["agents"][0]["metadata"])
    assert meta == {"user_id": uid}
    for bad in ("xx", "MR", "hindi", "<script>", ""):
        assert client.post("/livekit/token", json={"user_id": uid, "language": bad}).status_code == 422, bad
