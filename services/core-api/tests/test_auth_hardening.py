"""Deadline hardening (2026-11-10): closed sign-up, sign-up rate limit, household scoping of the query-keyed routes, the
Origin (CSRF) brake and a real logout. Two synthetic households; no real data."""

import pytest
from core_api import auth, baseurl
from core_api.origin_guard import origin_allowed

PW = "synthetic-password-123"
CODE = "demo-signup-code-2026"


@pytest.fixture(autouse=True)
def _closed_signup(monkeypatch):
    monkeypatch.setenv("ARJUN_AUTH", "1")
    monkeypatch.delenv("ARJUN_ALLOW_OPEN_SIGNUP", raising=False)
    monkeypatch.setenv("ARJUN_SIGNUP_CODE", CODE)
    auth.reset_auth_limits_for_tests()
    baseurl.reset()


def signup(client, email, code=CODE, **kw):
    body = {"email": email, "password": PW, "name": "Synthetic"}
    if code is not None:
        body["signup_code"] = code
    return client.post("/auth/signup", json=body, **kw)


def login(client, email):
    client.cookies.clear()
    r = client.post("/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200, r.text


def parent(client, name):
    r = client.post("/parents", json={"name": name, "age": 72, "contacts": []})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---- 2. closed sign-up ---------------------------------------------------------------------------------------
def test_signup_needs_the_code_even_for_the_first_account(client):
    assert signup(client, "first@example.test", code=None).status_code == 403
    assert signup(client, "first@example.test", code="wrong-code").status_code == 403
    assert client.get("/auth/me").status_code == 401  # nothing was created
    assert signup(client, "first@example.test").status_code == 201


def test_signup_is_closed_when_no_code_is_configured(client, monkeypatch):
    monkeypatch.delenv("ARJUN_SIGNUP_CODE")
    r = signup(client, "a@example.test")
    assert r.status_code == 403 and r.json()["detail"] == "sign-up is closed"


def test_open_signup_is_a_dev_switch(client, monkeypatch):
    monkeypatch.delenv("ARJUN_SIGNUP_CODE")
    monkeypatch.setenv("ARJUN_ALLOW_OPEN_SIGNUP", "1")
    assert signup(client, "dev@example.test", code=None).status_code == 201


def test_a_wrong_code_cannot_probe_which_emails_exist(client):
    assert signup(client, "taken@example.test").status_code == 201
    client.cookies.clear()
    assert signup(client, "taken@example.test", code="wrong").status_code == 403  # not 409
    assert signup(client, "taken@example.test").status_code == 409  # with the code the duplicate is reported


def test_signup_is_limited_to_five_attempts_a_minute(client):
    codes = [signup(client, f"x{i}@example.test", code="wrong").status_code for i in range(7)]
    assert codes == [403] * 5 + [429] * 2
    assert signup(client, "ok@example.test").status_code == 429  # even the right code: the window is per IP


def test_the_signup_code_is_never_echoed(client):
    r = signup(client, "a@example.test", code="wrong")
    assert CODE not in r.text and "wrong" not in r.text


# ---- 1. logout ------------------------------------------------------------------------------------------------
def test_logout_is_a_204_that_expires_the_cookie_and_kills_the_session(client):
    assert signup(client, "out@example.test").status_code == 201
    r = client.post("/auth/logout")
    assert r.status_code == 204 and r.content == b""
    cookie = r.headers["set-cookie"].lower()
    assert "arjun_session=" in cookie and ("max-age=0" in cookie or "1970" in cookie) and "httponly" in cookie
    assert client.get("/auth/me").status_code == 401


# ---- 3. household scoping of the query-keyed routes ----------------------------------------------------------------
@pytest.fixture()
def households(client):
    """Account A owns elder A; account B owns elder B; account C is only FAMILY of elder A (accepted A's invite)."""
    assert signup(client, "a@example.test").status_code == 201
    elder_a = parent(client, "Elder A")
    invite = client.post(f"/parents/{elder_a}/invite").json()["url"].split("token=")[-1]
    client.cookies.clear()
    assert signup(client, "b@example.test").status_code == 201
    elder_b = parent(client, "Elder B")
    client.cookies.clear()
    assert signup(client, "c@example.test").status_code == 201
    assert client.post("/auth/accept-invite", json={"token": invite}).status_code == 200
    return elder_a, elder_b


def test_a_session_cannot_use_another_households_elder_on_query_keyed_routes(client, households):
    elder_a, elder_b = households
    login(client, "b@example.test")
    assert client.get(f"/media/news?user_id={elder_a}").status_code == 403
    assert client.get(f"/media/youtube/search?q=bhajan&user_id={elder_a}").status_code == 403
    assert client.get("/media/news?user_id=abc").status_code == 403
    assert client.get("/media/news").status_code == 403  # no elder named: not allowed either
    assert client.get(f"/media/news?user_id={elder_b}").status_code == 200  # her own elder
    assert client.get(f"/media/youtube/search?q=bhajan&user_id={elder_b}").status_code != 403  # 503 here: no YouTube key


def test_a_family_member_may_use_the_elder_they_were_invited_to_and_nothing_else(client, households):
    elder_a, elder_b = households
    login(client, "c@example.test")
    assert client.get(f"/media/news?user_id={elder_a}").status_code == 200
    assert client.get(f"/media/news?user_id={elder_b}").status_code == 403


def test_household_wide_routes_are_owner_only(client, households):
    login(client, "a@example.test")
    assert client.get("/metrics/voice?hours=24").status_code == 200
    assert client.get("/diag/base-url").status_code == 200
    login(client, "c@example.test")  # family only, owns no elder
    assert client.get("/metrics/voice?hours=24").status_code == 403
    assert client.get("/diag/base-url").status_code == 403
    assert client.get("/media/status").status_code == 200  # the harmless status route stays open to any family session


def test_without_a_session_those_routes_are_401(client, households):
    client.cookies.clear()
    for path in ("/media/news?user_id=1", "/metrics/voice", "/diag/base-url"):
        assert client.get(path).status_code == 401


# ---- 4. the Origin (CSRF) brake --------------------------------------------------------------------------------
def test_origin_rule():
    base = "https://odin.tail7a9105.ts.net"
    for ok in ("http://localhost:5173", "http://127.0.0.1:8000", "https://localhost", base, base + ":443"):
        assert origin_allowed(ok, base), ok
    for bad in ("https://evil.example", "null", "", "http://odin.tail7a9105.ts.net", "https://odin.tail7a9105.ts.net:8443",
                "https://odin.tail7a9105.ts.net.evil.example", "ftp://localhost"):
        assert not origin_allowed(bad, base), bad
    assert not origin_allowed("https://x.trycloudflare.com", "")  # no BASE_URL: only localhost


def test_a_cross_site_post_with_a_session_cookie_is_refused(client, monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://family.example.test")
    assert signup(client, "csrf@example.test").status_code == 201
    body = {"name": "Elder", "age": 70, "contacts": []}
    assert client.post("/parents", json=body, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/parents", json=body, headers={"Origin": "null"}).status_code == 403
    assert client.patch("/parents/1", json={"name": "x"}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.delete("/parents/1", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/parents", json=body, headers={"Origin": "http://localhost:5173"}).status_code == 201
    assert client.post("/parents", json=body, headers={"Origin": "https://family.example.test"}).status_code == 201
    assert client.post("/parents", json=body).status_code == 201  # no Origin at all (curl / a service): allowed


def test_safe_methods_and_the_login_page_itself_are_not_blocked_by_origin(client):
    assert signup(client, "get@example.test").status_code == 201
    assert client.get("/auth/me", headers={"Origin": "https://evil.example"}).status_code == 200
    # a cross-site LOGIN attempt carries no session yet but auth is on: refused as well
    assert client.post("/auth/login", json={"email": "get@example.test", "password": PW}, headers={"Origin": "https://evil.example"}).status_code == 403


def test_service_calls_without_auth_or_cookies_are_never_affected(client, monkeypatch):
    monkeypatch.setenv("ARJUN_AUTH", "0")  # today's demo mode: the key-injecting proxy, no account cookies
    r = client.post("/users", json={"name": "Aaji", "language": "mr"}, headers={"Origin": "https://some-tunnel.example"})
    assert r.status_code == 201
