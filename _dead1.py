import sys

sys.stdout.reconfigure(encoding="utf-8")


def edit(p, pairs, create_missing=False):
    s = open(p, encoding="utf-8", newline="").read()
    crlf = "\r\n" in s
    s = s.replace("\r\n", "\n")
    for a, b in pairs:
        assert s.count(a) == 1, (p, a[:70], s.count(a))
        s = s.replace(a, b)
    open(p, "w", encoding="utf-8", newline="\r\n" if crlf else "\n").write(s)


C = "D:/Arjun/services/core-api/"
edit(C + "core_api/telegram.py", [
    ("from . import models as m\n", "from . import baseurl\nfrom . import models as m\n"),
    ("    ok = False\n    try:\n        ok = _post(text, join_url, button_text)",
     "    ok = False\n    try:\n        # a dead / refused BASE_URL must never reach the family as a button (2026-11-09): the alert goes out as text\n"
     "        join_url, extra = baseurl.guard_link(join_url)\n        if extra:\n            text = f\"{text}\\n{extra}\"\n        ok = _post(text, join_url, button_text)"),
])
edit(C + "core_api/video_calls.py", [
    ("from . import joins, telegram\n", "from . import baseurl, joins, telegram\n"),
    ('    call = m.VideoCall(user_id=user_id, contact_id=contact.id, mode="video", status="ringing", created_at=now)\n    db.add(call)\n    db.commit()\n    db.refresh(call)\n    user = db.get(m.User, user_id)\n    elder = (user.name if user else "आजी").split("(", 1)[0].strip()\n    telegram.send_alert(\n        f"📹',
     '    if baseurl.configured() and not baseurl.check()["ok"]:\n'
     '        # the family could not open the join link: say so (text only) and tell the elder the call did not connect\n'
     '        who = (db.get(m.User, user_id).name if db.get(m.User, user_id) else "आजी").split("(", 1)[0].strip()\n'
     '        telegram.send_alert(\n            f"📹 {who} व्हिडिओ कॉल करत होत्या. {baseurl.LINK_DOWN_TEXT}", None, user_id=user_id,\n'
     '            kind="video_call_link_down", bind=db.get_bind(),\n        )\n'
     '        raise HTTPException(503, "family call link unavailable (BASE_URL not reachable)")\n'
     '    call = m.VideoCall(user_id=user_id, contact_id=contact.id, mode="video", status="ringing", created_at=now)\n    db.add(call)\n    db.commit()\n    db.refresh(call)\n    user = db.get(m.User, user_id)\n    elder = (user.name if user else "आजी").split("(", 1)[0].strip()\n    telegram.send_alert(\n        f"📹'),
])
edit(C + "core_api/main.py", [
    ("@asynccontextmanager\nasync def lifespan(_: FastAPI):  # type: ignore[no-untyped-def]\n    check_api_key_configured()  # refuse to start with auth silently disabled\n",
     "def _log_base_url_status() -> None:\n    \"\"\"One startup line: BASE_URL ok / unreachable / quick-tunnel (no secrets). Off the request path: the probe can take 3 s.\"\"\"\n"
     "    line = baseurl.status_line()\n    (logging.getLogger(\"uvicorn.error\").info if line.startswith(\"BASE_URL ok\") else logging.getLogger(\"uvicorn.error\").warning)(line)\n    print(line, flush=True)\n\n\n"
     "@asynccontextmanager\nasync def lifespan(_: FastAPI):  # type: ignore[no-untyped-def]\n    check_api_key_configured()  # refuse to start with auth silently disabled\n"
     "    if not os.environ.get(\"ARJUN_TESTING\"):\n        threading.Thread(target=_log_base_url_status, name=\"base-url-check\", daemon=True).start()\n"),
    ('@app.get("/health")\ndef health() -> dict[str, str]:\n    return {"status": "ok"}\n',
     '@app.get("/health")\ndef health() -> dict[str, str]:\n    return {"status": "ok"}\n\n\n'
     '@router.get("/diag/base-url")\ndef diag_base_url() -> dict[str, object]:\n'
     '    """Can the family open the join links Arjun sends? Family session (or the service API key) only; no secrets in the answer."""\n'
     '    v = baseurl.check()\n    return {"url": v["url"], "https": v["https"], "reachable": v["reachable"], "kind": v["kind"], "ok": v["ok"],\n'
     '            "reason": v["reason"], "hint": baseurl.FIX_HINT}\n'),
])
edit(C + "tests/conftest.py", [
    ("import pytest  # noqa: E402\n", "import pytest  # noqa: E402\nfrom core_api import baseurl  # noqa: E402\n"),
    ("@pytest.fixture()\ndef client():", "@pytest.fixture(autouse=True)\ndef _base_url_probe(monkeypatch):\n    \"\"\"The BASE_URL reachability probe never touches the network in tests: every URL answers 200 unless a test says otherwise.\"\"\"\n    baseurl.reset()\n    monkeypatch.setattr(baseurl, \"_fetch\", lambda url, timeout: 200)\n    monkeypatch.delenv(\"ARJUN_ALLOW_QUICK_TUNNEL\", raising=False)\n    yield\n    baseurl.reset()\n\n\n@pytest.fixture()\ndef client():"),
])
edit("D:/Arjun/.env.example", [
    ("BASE_URL=\n", "BASE_URL=\n# core-api refuses to put a *.trycloudflare.com quick-tunnel URL in family links (they die when the tunnel restarts).\n# 1 = allow it anyway (scripts/dev-up.ps1 -Phone sets this for core-api itself; nothing is written here).\nARJUN_ALLOW_QUICK_TUNNEL=\n"),
])
edit("D:/Arjun/web/src/elder/useAppActions.ts", [
    ('voice.sendText("कॉल जोडता आला नाही. पुन्हा प्रयत्न करा.")', 'voice.sendText("कॉल लागला नाही, मी पुन्हा प्रयत्न करतो.")'),
])
print("ok")
