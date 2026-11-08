"""Consent-first cloned voices: the recording is never stored, the embedding is encrypted, one active voice. No network."""

import base64

import pytest
from core_api import models as m
from core_api import voices
from cryptography.fernet import Fernet

AUDIO = base64.b64encode(b"\x01" * 20_000).decode()


@pytest.fixture(autouse=True)
def fake_gnani(monkeypatch):
    monkeypatch.setenv("VOICE_CLONE_KEY", Fernet.generate_key().decode())
    calls = []

    def fake(audio, mime):
        calls.append((len(audio), mime))
        return {"embedding": "EMB-" + str(len(calls)), "shape": [1, 768], "dtype": "torch.bfloat16"}

    monkeypatch.setattr(voices, "create_embedding", fake)
    return calls


def add(client, uid, **over):
    body = {"name": "Rahul", "relation": "son", "consent": True, "consent_by": "Rahul Patil",
            "audio_base64": AUDIO, "mime": "audio/webm"} | over
    return client.post(f"/users/{uid}/voices", json=body)


def test_add_first_voice_is_active_and_embedding_is_encrypted(client, uid, fake_gnani):
    r = add(client, uid)
    assert r.status_code == 201
    row = r.json()
    assert row["active"] is True and row["name"] == "Rahul" and "embedding" not in row
    assert fake_gnani == [(20_000, "audio/webm")]
    from core_api.db import get_db
    from core_api.main import app

    db = next(app.dependency_overrides[get_db]())
    stored = db.get(m.ClonedVoice, row["id"])
    assert b"EMB-1" not in stored.embedding_enc  # encrypted at rest
    assert client.get(f"/internal/users/{uid}/cloned-voice").json()["embedding"] == "EMB-1"


def test_consent_is_required(client, uid, fake_gnani):
    assert add(client, uid, consent=False).status_code == 422
    assert fake_gnani == []


def test_too_short_recording_is_refused_without_calling_gnani(client, uid, fake_gnani):
    assert add(client, uid, audio_base64=base64.b64encode(b"x" * 100).decode()).status_code == 422
    assert fake_gnani == []


def test_without_key_it_is_unavailable(client, uid, monkeypatch):
    monkeypatch.delenv("VOICE_CLONE_KEY")
    assert add(client, uid).status_code == 503


def test_only_one_active_voice_and_label_follows(client, uid):
    a = add(client, uid).json()
    b = add(client, uid, name="Priya", relation="daughter", consent_by="Priya").json()
    assert b["active"] is False
    assert client.get(f"/users/{uid}/voice-label").json() == {"name": "Rahul", "relation": "son"}
    client.post(f"/users/{uid}/voices/{b['id']}/activate")
    active = [v["name"] for v in client.get(f"/users/{uid}/voices").json() if v["active"]]
    assert active == ["Priya"]
    client.post(f"/users/{uid}/voices/{b['id']}/deactivate")
    assert client.get(f"/users/{uid}/voice-label").json()["name"] is None
    assert client.get(f"/internal/users/{uid}/cloned-voice").status_code == 404
    assert a["id"] != b["id"]


def test_delete_removes_voice_but_keeps_audit(client, uid):
    v = add(client, uid).json()
    assert client.post(f"/internal/users/{uid}/cloned-voice/{v['id']}/used").status_code == 204
    assert client.get(f"/users/{uid}/voices").json()[0]["use_count"] == 1
    assert client.delete(f"/users/{uid}/voices/{v['id']}").status_code == 204
    assert client.get(f"/users/{uid}/voices").json() == []
    events = [e["event"] for e in client.get(f"/users/{uid}/voices/audit").json()]
    assert events == ["deleted", "used", "activated", "added"]


def test_other_elders_voice_is_not_reachable(client, uid):
    v = add(client, uid).json()
    other = client.post("/users", json={"name": "Other", "interests": []}).json()["id"]
    assert client.delete(f"/users/{other}/voices/{v['id']}").status_code == 404


def test_gnani_key_only_in_create_embedding():
    """CLAUDE.md rule 12 exception: GNANI_API_KEY is read in core-api only inside voices.create_embedding."""
    import ast
    import pathlib

    root = pathlib.Path(voices.__file__).parent
    users = [p.name for p in root.glob("*.py") if "GNANI_API_KEY" in p.read_text(encoding="utf-8")]
    assert users == ["voices.py"]
    src = pathlib.Path(voices.__file__).read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "create_embedding")
    assert src.count("GNANI_API_KEY") == (ast.get_source_segment(src, fn) or "").count("GNANI_API_KEY") > 0
