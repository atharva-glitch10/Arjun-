"""The same hardening against a REAL running core-api (uvicorn in a subprocess, temp SQLite file, random service key), not
only the in-process TestClient: the logout bug of 2026-11-10 (the server dropped the connection) was invisible to TestClient."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

PW = "synthetic-password-123"
CODE = "live-signup-code-2026"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def live(tmp_path):
    # one server per test: the sign-up limit (5 a minute per IP) is per process, so tests must not share it
    db = tmp_path / "auth.db"
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {
        **{k: v for k, v in os.environ.items() if k not in ("ARJUN_TESTING", "BASE_URL", "TELEGRAM_ENABLED")},
        "DATABASE_URL": f"sqlite:///{db.as_posix()}", "CORE_API_KEY": "live-test-key-" + "x" * 24, "ARJUN_AUTH": "1",
        "ARJUN_SIGNUP_CODE": CODE, "ARJUN_TZ": "Asia/Kolkata", "PYTHONUNBUFFERED": "1",
    }
    env.pop("ARJUN_ALLOW_OPEN_SIGNUP", None)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "core_api.main:app", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                if httpx.get(base + "/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        else:
            pytest.fail("the live core-api did not start")
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _signup(c, email, code=CODE):
    body = {"email": email, "password": PW, "name": "Synthetic", **({"signup_code": code} if code else {})}
    return c.post("/auth/signup", json=body)


def test_live_logout_is_a_real_204_that_expires_the_cookie(live):
    with httpx.Client(base_url=live, timeout=15) as c:
        assert _signup(c, "logout@example.test").status_code == 201
        assert c.get("/auth/me").status_code == 200
        r = c.post("/auth/logout")  # used to raise RemoteProtocolError: the server dropped the connection
        assert r.status_code == 204 and r.content == b""
        sc = r.headers["set-cookie"].lower()
        assert "arjun_session=" in sc and ("max-age=0" in sc or "1970" in sc) and "httponly" in sc
        assert c.cookies.get("arjun_session") is None  # the client really dropped it
        assert c.get("/auth/me").status_code == 401


def test_live_signup_is_closed_without_the_code_and_open_with_it(live):
    with httpx.Client(base_url=live, timeout=15) as c:
        assert _signup(c, "nocode@example.test", code=None).status_code == 403
        assert _signup(c, "badcode@example.test", code="nope").status_code == 403
        assert c.get("/auth/me").status_code == 401
        assert _signup(c, "withcode@example.test").status_code == 201


def test_live_cross_household_and_origin_brake(live):
    with httpx.Client(base_url=live, timeout=15) as a, httpx.Client(base_url=live, timeout=15) as b:
        assert _signup(a, "hh-a@example.test").status_code == 201
        assert _signup(b, "hh-b@example.test").status_code == 201
        elder_a = a.post("/parents", json={"name": "Elder A", "age": 70, "contacts": []}).json()["id"]
        elder_b = b.post("/parents", json={"name": "Elder B", "age": 70, "contacts": []}).json()["id"]
        assert b.get(f"/users/{elder_a}").status_code == 403
        assert b.get(f"/media/news?user_id={elder_a}").status_code == 403  # was 200 before the hardening
        assert b.get(f"/media/news?user_id={elder_b}").status_code == 200
        assert b.get("/metrics/voice").status_code == 200  # b owns an elder
        # a forged cross-site POST with a valid cookie
        r = b.post("/parents", json={"name": "x", "age": 70, "contacts": []}, headers={"Origin": "https://evil.example"})
        assert r.status_code == 403
        assert b.post("/parents", json={"name": "y", "age": 70, "contacts": []}, headers={"Origin": "http://localhost:5173"}).status_code == 201


def test_live_signup_rate_limit(live):
    with httpx.Client(base_url=live, timeout=15) as c:
        codes = [_signup(c, f"flood{i}@example.test", code="wrong").status_code for i in range(8)]
    assert codes == [403] * 5 + [429] * 3
