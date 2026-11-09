"""BASE_URL guard (2026-11-09): a dead / refused URL is never sent to the family as a join link. HTTP is mocked."""

import httpx
import pytest
from core_api import baseurl, telegram, video_calls

DEAD = "https://dead-name.trycloudflare.com"
FUNNEL = "https://odin.tail7a9105.ts.net"


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def fetcher(monkeypatch, status=200, exc: Exception | None = None):
    calls: list[str] = []

    def f(url, timeout):
        calls.append(url)
        assert timeout <= 3.0  # the probe is capped at 3 s
        if exc is not None:
            raise exc
        return status

    monkeypatch.setattr(baseurl, "_fetch", f)
    return calls


# ---- the check ----------------------------------------------------------------------------------------------
def test_a_dead_url_is_unreachable_and_says_why(monkeypatch):
    calls = fetcher(monkeypatch, exc=httpx.ConnectError("NXDOMAIN"))
    v = baseurl.check("https://odin.example.test")
    assert v == {"url": "https://odin.example.test", "https": True, "reachable": False, "kind": "https", "ok": False,
                 "reason": "BASE_URL is unreachable (ConnectError)"}
    assert calls == ["https://odin.example.test/"]


def test_a_quick_tunnel_is_blocked_without_the_opt_in_and_never_probed(monkeypatch):
    calls = fetcher(monkeypatch)
    v = baseurl.check(DEAD)
    assert v["kind"] == "quick-tunnel" and v["ok"] is False and v["reachable"] is False
    assert "ARJUN_ALLOW_QUICK_TUNNEL=1" in v["reason"] and calls == []


def test_a_quick_tunnel_is_allowed_with_the_opt_in_but_must_still_answer(monkeypatch):
    monkeypatch.setenv("ARJUN_ALLOW_QUICK_TUNNEL", "1")
    fetcher(monkeypatch)
    assert baseurl.check(DEAD)["ok"] is True
    baseurl.reset()
    fetcher(monkeypatch, exc=httpx.ConnectError("NXDOMAIN"))
    v = baseurl.check(DEAD)
    assert v["ok"] is False and v["kind"] == "quick-tunnel" and "unreachable" in v["reason"]


def test_a_good_https_url_is_ok_including_the_tailscale_funnel(monkeypatch):
    fetcher(monkeypatch)
    v = baseurl.check(FUNNEL + "/")
    assert v["ok"] is True and v["reachable"] is True and v["https"] is True and v["kind"] == "tailscale" and v["url"] == FUNNEL
    assert baseurl.status_line(v) == f"BASE_URL ok: {FUNNEL} (tailscale)"


@pytest.mark.parametrize("url,kind", [("", "none"), ("http://192.168.1.5:5173", "http"), ("not a url", "invalid")])
def test_empty_http_and_invalid_urls_are_not_ok(monkeypatch, url, kind):
    calls = fetcher(monkeypatch)
    v = baseurl.check(url)
    assert v["kind"] == kind and v["ok"] is False and calls == []


def test_a_5xx_answer_counts_as_unreachable(monkeypatch):
    fetcher(monkeypatch, status=530)  # what Cloudflare answers when the tunnel's origin is gone
    v = baseurl.check("https://x.example.test")
    assert v["ok"] is False and v["reason"] == "BASE_URL answered HTTP 530"
    fetcher(monkeypatch, status=404)  # a 404 still proves the host is up
    baseurl.reset()
    assert baseurl.check("https://x.example.test")["ok"] is True


def test_the_verdict_is_cached_for_sixty_seconds(monkeypatch):
    calls = fetcher(monkeypatch)
    c = Clock()
    for _ in range(3):
        baseurl.check(FUNNEL, clock=c)
    assert len(calls) == 1
    c.t += 59
    baseurl.check(FUNNEL, clock=c)
    assert len(calls) == 1
    c.t += 2
    baseurl.check(FUNNEL, clock=c)
    assert len(calls) == 2


def test_the_startup_line_names_the_state_and_the_fix(monkeypatch):
    fetcher(monkeypatch, exc=httpx.ConnectError("x"))
    line = baseurl.status_line(baseurl.check("https://gone.example.test"))
    assert line.startswith("BASE_URL unreachable:") and "odin.tail7a9105.ts.net" in line
    assert baseurl.status_line(baseurl.check(DEAD)).startswith("BASE_URL quick-tunnel:")
    assert baseurl.status_line(baseurl.check("")).startswith("BASE_URL not-set:")


# ---- what the family receives -------------------------------------------------------------------------------
@pytest.fixture()
def tg(monkeypatch):
    telegram.reset_for_tests()
    monkeypatch.setenv("TELEGRAM_ENABLED", "1")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")
    monkeypatch.setenv("JOIN_SECRET", "test-secret")
    posts: list[dict] = []

    class Resp:
        status_code = 200

        def json(self):
            return {"ok": True}

    monkeypatch.setattr(telegram.httpx, "post", lambda url, json=None, timeout=None: posts.append(json or {}) or Resp())
    yield posts
    telegram.reset_for_tests()


def test_a_dead_url_sends_the_alert_as_text_with_no_button_and_logs_the_reason(client, uid, tg, monkeypatch, caplog):
    monkeypatch.setenv("BASE_URL", DEAD)  # a quick tunnel, not allowed
    with caplog.at_level("WARNING", logger="arjun.baseurl"):
        client.post(f"/users/{uid}/distress", params={"kind": "emergency"})
        telegram.wait_idle()
    assert len(tg) == 1 and "reply_markup" not in tg[0]  # the emergency alert itself still goes out
    assert tg[0]["text"].startswith("🚨") and baseurl.LINK_DOWN_TEXT in tg[0]["text"]
    assert any("family call link NOT sent (quick-tunnel)" in r.message for r in caplog.records)
    assert "test-token" not in caplog.text


def test_an_unreachable_https_url_also_sends_no_button(client, uid, tg, monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://gone.example.test")
    fetcher(monkeypatch, exc=httpx.ConnectError("NXDOMAIN"))
    client.post(f"/users/{uid}/distress", params={"kind": "emergency"})
    telegram.wait_idle()
    assert "reply_markup" not in tg[0] and baseurl.LINK_DOWN_TEXT in tg[0]["text"]


def test_a_good_url_keeps_the_join_button_and_adds_no_warning(client, uid, tg, monkeypatch):
    monkeypatch.setenv("BASE_URL", FUNNEL)
    fetcher(monkeypatch)
    client.post(f"/users/{uid}/distress", params={"kind": "emergency"})
    telegram.wait_idle()
    assert tg[0]["reply_markup"]["inline_keyboard"][0][0]["url"].startswith(FUNNEL + "/?view=join&t=")
    assert baseurl.LINK_DOWN_TEXT not in tg[0]["text"]


# ---- the elder's video call ---------------------------------------------------------------------------------
def _room(client, uid):
    from test_video_calls import _room as room

    return room(client, uid)


def test_a_video_call_with_a_dead_link_is_refused_so_the_elder_hears_it_did_not_connect(client, uid, monkeypatch):
    from test_video_calls import _contact

    _room(client, uid)
    contact = _contact(client, uid)
    monkeypatch.setenv("BASE_URL", DEAD)
    sent = []
    monkeypatch.setattr(video_calls.telegram, "send_alert", lambda *a, **kw: sent.append((a, kw)) or True)
    r = client.post(f"/users/{uid}/calls", json={"contact_id": contact["id"], "mode": "video"})
    assert r.status_code == 503 and "link unavailable" in r.json()["detail"]
    assert len(sent) == 1 and sent[0][0][1] is None and baseurl.LINK_DOWN_TEXT in sent[0][0][0]  # text only, no link
    assert sent[0][1]["kind"] == "video_call_link_down"


def test_a_video_call_without_any_base_url_still_works_as_before(client, uid, monkeypatch):
    from test_video_calls import _contact

    _room(client, uid)
    contact = _contact(client, uid)
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.setattr(video_calls.telegram, "send_alert", lambda *a, **kw: True)
    assert client.post(f"/users/{uid}/calls", json={"contact_id": contact["id"], "mode": "video"}).status_code == 201


# ---- the diagnostics endpoint -----------------------------------------------------------------------------
def test_diag_base_url_reports_the_verdict_and_a_hint(client, monkeypatch):
    monkeypatch.setenv("BASE_URL", DEAD)
    d = client.get("/diag/base-url").json()
    assert d["url"] == DEAD and d["https"] is True and d["reachable"] is False and d["kind"] == "quick-tunnel" and d["ok"] is False
    assert "ts.net" in d["hint"] and "quick tunnel" in d["reason"]
    monkeypatch.setenv("BASE_URL", FUNNEL)
    baseurl.reset()
    ok = client.get("/diag/base-url").json()
    assert ok["ok"] is True and ok["kind"] == "tailscale"
