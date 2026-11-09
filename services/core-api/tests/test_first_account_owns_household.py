def _signup(client, email):
    return client.post("/auth/signup", json={"email": email, "password": "synthetic-password-123", "name": "Family"})


def test_first_account_owns_existing_elders_second_sees_none(client, monkeypatch, uid):
    monkeypatch.setenv("ARJUN_AUTH", "1")
    assert _signup(client, "first@example.test").status_code == 201
    assert [e["id"] for e in client.get("/auth/me").json()["elders"]] == [uid]
    client.cookies.clear()
    assert _signup(client, "second@example.test").status_code == 201
    assert client.get("/auth/me").json()["elders"] == []
