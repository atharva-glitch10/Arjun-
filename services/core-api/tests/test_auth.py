from __future__ import annotations

import os

from core_api.auth import reset_auth_limits_for_tests


def _signup(client, email: str = "family@example.test"):
    return client.post("/auth/signup", json={"email": email, "password": "synthetic-password-123", "name": "Family"})


def _parent(client, name: str = "Synthetic Aaji"):
    response = client.post("/parents", json={"name": name, "age": 72, "contacts": []})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_signup_login_session_cookie_and_logout(client, monkeypatch):
    monkeypatch.setenv("ARJUN_AUTH", "1")
    response = _signup(client, "  FAMILY@EXAMPLE.TEST ")
    assert response.status_code == 201
    assert response.json()["email"] == "family@example.test"
    cookie = response.headers["set-cookie"].lower()
    assert "arjun_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/auth/me").json()["account"]["email"] == "family@example.test"
    client.post("/auth/logout")
    assert client.get("/auth/me").status_code == 401


def test_family_membership_isolation_and_paired_device_access(client, monkeypatch):
    monkeypatch.setenv("ARJUN_AUTH", "1")
    first = _signup(client)
    assert first.status_code == 201
    parent_a = _parent(client)
    pairing = client.post(f"/parents/{parent_a}/pairing")
    assert pairing.status_code == 201
    paired = client.post("/devices/pair", json={"code": pairing.json()["code"], "label": "Synthetic phone"})
    assert paired.status_code == 200
    device_cookie = client.cookies.get("arjun_device")
    assert device_cookie

    # Owner membership permits family data and the shared read route.
    assert client.get(f"/users/{parent_a}").status_code == 200
    assert client.get(f"/users/{parent_a}/contacts").status_code == 200
    # Raw story records remain outside the family dashboard surface.
    assert client.get(f"/users/{parent_a}/stories/latest").status_code == 403

    client.post("/auth/logout")
    second = _signup(client, "other@example.test")
    assert second.status_code == 201
    parent_b = _parent(client, "Other Aaji")
    assert client.get(f"/users/{parent_a}/memory-book").status_code == 403
    assert client.get(f"/users/{parent_a}/feed").status_code == 403
    assert client.get(f"/users/{parent_b}").status_code == 200

    # The elder device cookie is bound to its paired elder and cannot read family-only paths.
    client.post("/auth/logout")
    client.cookies.set("arjun_device", device_cookie)
    assert client.get(f"/users/{parent_a}/day").status_code == 200
    assert client.get(f"/users/{parent_b}/day").status_code == 403
    assert client.get(f"/users/{parent_a}/memory-book").status_code == 403


def test_api_key_compatibility_when_auth_is_disabled(client, monkeypatch):
    monkeypatch.setenv("ARJUN_AUTH", "0")
    os.environ.pop("CORE_API_KEY", None)
    response = client.post("/users", json={"name": "Synthetic Aaji"})
    assert response.status_code == 201


def test_login_limit_and_generic_failure(client, monkeypatch):
    monkeypatch.setenv("ARJUN_AUTH", "1")
    reset_auth_limits_for_tests()
    _signup(client)
    failures = [
        client.post("/auth/login", json={"email": "family@example.test", "password": "wrong-password"})
        for _ in range(5)
    ]
    assert all(row.status_code == 401 and row.json()["detail"] == "invalid email or password" for row in failures)
    blocked = client.post("/auth/login", json={"email": "family@example.test", "password": "wrong-password"})
    assert blocked.status_code == 429 and blocked.headers["retry-after"] == "60"
