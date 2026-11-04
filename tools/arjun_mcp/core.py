"""Arjun tools for outside AIs (Claude Code, Claude desktop, OpenCode...). Plain functions, tested without MCP.

Read-only by default; write tools need ARJUN_MCP_WRITE=1. Every result passes `redact`: no key, token or full phone
number ever leaves this process. Family tools give summaries only, never her words (CLAUDE.md privacy rules)."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ("core-api", "reasoning", "voice-agent", "scheduler", "web", "tunnel")
TEST_USER_NAME = "MCP Test"
_TRANSCRIPT_KEYS = {"transcript", "utterance", "user_text", "said", "stt_text", "turns"}
STATE = Path(__file__).resolve().parent / "state.json"


def env() -> dict[str, str]:
    vals = {k: v or "" for k, v in dotenv_values(ROOT / ".env").items()}
    return {**vals, **{k: v for k, v in os.environ.items() if k.startswith(("ARJUN_", "CORE_", "REASONING_"))}}


_SECRET_NAMES = ("KEY", "SECRET", "TOKEN", "PASSWORD", "CHAT_ID", "ACCESS_CODE")
_PATTERNS = [
    re.compile(r"sk_[A-Za-z0-9_]{8,}"),
    re.compile(r"\bAC[0-9a-f]{32}\b"),
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b"),  # Telegram bot token
    re.compile(r"\bvach_[A-Za-z0-9_]{10,}"),
    re.compile(r"\bAPI[A-Za-z0-9]{10,}\b"),
]
_PHONE = re.compile(r"(?<!\d)(\+?\d[\d \-]{7,14}\d)(?!\d)")


def redact(text: str, e: dict[str, str] | None = None) -> str:
    e = env() if e is None else e
    for name, value in e.items():
        if value and len(value) >= 6 and any(s in name.upper() for s in _SECRET_NAMES):
            text = text.replace(value, "[redacted]")
    for p in _PATTERNS:
        text = p.sub("[redacted]", text)
    return _PHONE.sub(lambda m: "…" + re.sub(r"\D", "", m.group(1))[-4:], text)


def _client(e: dict[str, str]) -> tuple[httpx.Client, str, str]:
    core = e.get("CORE_API_URL") or "http://127.0.0.1:8000"
    reasoning = e.get("REASONING_URL") or "http://127.0.0.1:8001"
    return httpx.Client(timeout=10, headers={"X-API-Key": e.get("CORE_API_KEY", "")}), core, reasoning


def _status(c: httpx.Client, url: str) -> str:
    try:
        return str(c.get(url).status_code)
    except httpx.HTTPError as exc:
        return f"down ({type(exc).__name__})"


def health() -> dict[str, Any]:
    """Is Arjun up? core-api, reasoning, web status, phone link, voice provider, Telegram, access lock."""
    e = env()
    c, core, reasoning = _client(e)
    provider = e.get("ARJUN_VOICE_PROVIDER", "gnani")
    return {
        "core_api": _status(c, f"{core}/health"),
        "reasoning": _status(c, f"{reasoning}/health"),
        "web": _status(c, "http://127.0.0.1:5173/"),
        "base_url": redact(e.get("BASE_URL", "")) or "(not set)",
        "voice_provider": provider if provider in ("gnani", "sarvam") else "INVALID VALUE (must be gnani or sarvam)",
        "telegram": e.get("TELEGRAM_ENABLED", "0"),
        "access_lock": "on" if len(e.get("ARJUN_ACCESS_CODE", "")) >= 6 else "OFF",
    }


def logs(service: str, tail: int = 80, grep: str | None = None) -> str:
    """Newest log of a service (core-api|reasoning|voice-agent|scheduler|web|tunnel), last `tail` lines, optional filter. Secrets and numbers redacted."""
    if service not in SERVICES:
        return f"unknown service; one of {', '.join(SERVICES)}"
    files = sorted((ROOT / "logs").glob(f"*{service}*.log"), key=lambda p: p.stat().st_mtime)
    if not files:
        return "no log file"
    lines = files[-1].read_text(encoding="utf-8", errors="replace").splitlines()
    if grep:
        lines = [ln for ln in lines if grep.lower() in ln.lower()]
    return redact("\n".join(lines[-max(1, min(tail, 500)):]))


def _test_user(c: httpx.Client, core: str) -> int:
    """A separate synthetic user for experiments, created once; its id is kept in state.json (not in git)."""
    import json

    if STATE.exists():
        uid = int(json.loads(STATE.read_text()).get("test_user_id", 0))
        if uid and c.get(f"{core}/users/{uid}").status_code == 200:
            return uid
    r = c.post(f"{core}/users", json={"name": TEST_USER_NAME, "language": "mr"})
    r.raise_for_status()
    uid = int(r.json()["id"])
    STATE.write_text(json.dumps({"test_user_id": uid}))
    return uid


def try_turn(text: str, user_id: int | None = None, confirm: bool = False) -> dict[str, Any]:
    """Send one sentence through reasoning. Default target is a separate test user; a real user needs confirm=True."""
    e = env()
    c, core, reasoning = _client(e)
    if user_id is not None and not confirm:
        return {"refused": "a real user needs confirm=True (it may create reminders or alert the family)"}
    uid = user_id if user_id is not None else _test_user(c, core)
    r = c.post(f"{reasoning}/turn", json={"user_id": uid, "text": text})
    if r.status_code != 200:
        return {"error": r.status_code, "detail": redact(r.text[:300], e)}
    d = r.json()
    out = {k: d.get(k) for k in ("reply", "intent", "mode", "source", "action")}
    out["route"] = (d.get("trace") or {}).get("route")
    out["user_id"] = uid
    return json_safe(out, e)


def run_tests(suite: str = "all") -> dict[str, str]:
    """Run a test suite (core-api|reasoning|voice-agent|scheduler|web|all); returns the last lines of each."""
    py = str(ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    if not Path(py).exists():
        py = "python"
    suites = {
        "core-api": ([py, "-m", "pytest", "-q"], "services/core-api"),
        "reasoning": ([py, "-m", "pytest", "-q"], "services/reasoning"),
        "voice-agent": ([py, "-m", "pytest", "-q"], "services/voice-agent"),
        "scheduler": ([py, "-m", "pytest", "-q"], "services/scheduler"),
        "web": (["npx", "vitest", "run"], "web"),
    }
    picked = suites if suite == "all" else {suite: suites[suite]} if suite in suites else {}
    if not picked:
        return {"error": f"suite one of {', '.join(suites)} or all"}
    out = {}
    for name, (cmd, cwd) in picked.items():
        p = subprocess.run(cmd, cwd=ROOT / cwd, capture_output=True, text=True, timeout=900, shell=os.name == "nt")
        tail = (p.stdout + p.stderr).strip().splitlines()[-15:]
        out[name] = redact("\n".join(tail))
    return out


def _uid(user_id: int) -> int:
    return int(user_id)


def today(user_id: int) -> Any:
    """Summary, mood, seriousness, check-ins, medicines: what the family dashboard shows. Never transcripts."""
    e = env()
    c, core, _ = _client(e)
    return json_safe(c.get(f"{core}/users/{_uid(user_id)}/wellbeing/today").json(), e)


def feed(user_id: int, limit: int = 30) -> Any:
    """Family feed events (alerts, check-ins, medicines) as the dashboard shows them."""
    e = env()
    c, core, _ = _client(e)
    rows = c.get(f"{core}/users/{_uid(user_id)}/feed").json()
    return json_safe(rows[-max(1, min(limit, 200)):] if isinstance(rows, list) else rows, e)


def medicines(user_id: int) -> Any:
    """Her medicine list and what is due now."""
    e = env()
    c, core, _ = _client(e)
    return json_safe({"medicines": c.get(f"{core}/users/{_uid(user_id)}/medicines").json(),
                      "due": c.get(f"{core}/users/{_uid(user_id)}/medicines/due").json()}, e)


def reminders_today(user_id: int) -> Any:
    """Today's reminders and their status."""
    e = env()
    c, core, _ = _client(e)
    return json_safe(c.get(f"{core}/users/{_uid(user_id)}/reminders/today").json(), e)


def writes_allowed() -> bool:
    return env().get("ARJUN_MCP_WRITE", "0") == "1"


def add_reminder(user_id: int, sentence: str) -> dict[str, Any]:
    """Add a reminder the same way she would say it (e.g. 'उद्या सकाळी ८ वाजता डॉक्टरकडे जायचं आठवण कर').
    Goes through Arjun's own understanding + read-back; needs ARJUN_MCP_WRITE=1."""
    if not writes_allowed():
        return {"refused": "write tools are off (set ARJUN_MCP_WRITE=1)"}
    return try_turn(sentence, user_id=user_id, confirm=True)


def json_safe(obj: Any, e: dict[str, str] | None = None) -> Any:
    """Drop transcript-like fields and redact every string."""
    e = env() if e is None else e
    if isinstance(obj, dict):
        return {k: json_safe(v, e) for k, v in obj.items() if k not in _TRANSCRIPT_KEYS}
    if isinstance(obj, list):
        return [json_safe(v, e) for v in obj]
    if isinstance(obj, str):
        return redact(obj, e)
    return obj
