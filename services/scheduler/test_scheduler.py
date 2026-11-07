import httpx
import scheduler


def _http(calls, briefing_text="सुप्रभात", opener_text="आजी, आज काय केलं?"):
    def handler(request):
        calls.append((request.method, request.url.path))
        path = request.url.path
        if path == "/internal/reminders/fire-due":
            return httpx.Response(200, json=[{"reminder_id": 1, "user_id": 1, "task": "doctor"}])
        if path == "/internal/medicines/tick":
            return httpx.Response(200, json={"reminded": [], "unconfirmed": []})
        if path == "/internal/checkins/tick":
            return httpx.Response(200, json={"asked": [], "followed_up": [], "closed": []})
        if path == "/internal/checkin-users":
            return httpx.Response(200, json=[])
        if path == "/internal/deliveries/sweep":
            return httpx.Response(200, json={"released": 0, "superseded": 0, "shown_only": 0, "notified": 0})
        if path == "/conversations/flush-idle":
            return httpx.Response(200, json={"sent": 1, "open": 0})
        if path == "/internal/briefings/send-due":
            return httpx.Response(200, json={"sent": 0, "failed": 0, "skipped": 0})
        if path.startswith("/briefing/"):
            return httpx.Response(200, json={"text": briefing_text})
        if path.startswith("/opener/"):
            return httpx.Response(200, json={"text": opener_text})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://x")


def _reset(monkeypatch, users):
    monkeypatch.setattr(scheduler, "CORE", "")
    monkeypatch.setattr(scheduler, "REASONING", "")
    monkeypatch.setattr(scheduler, "OPENER_USER_IDS", users)
    scheduler._opened_today.clear()


def test_tick_fires_reminders_and_meds(monkeypatch):
    _reset(monkeypatch, [])
    calls = []
    fired = scheduler.tick(_http(calls), "2026-10-24")
    assert fired == [{"reminder_id": 1, "user_id": 1, "task": "doctor"}]
    assert ("POST", "/internal/reminders/fire-due") in calls
    assert ("POST", "/internal/medicines/tick") in calls


def test_briefing_and_opener_at_most_once_per_day(monkeypatch):
    _reset(monkeypatch, [1])
    calls = []
    http = _http(calls)
    scheduler.tick(http, "2026-10-24")
    scheduler.tick(http, "2026-10-24")
    assert calls.count(("POST", "/internal/briefings/send-due")) == 2
    assert calls.count(("POST", "/opener/1")) == 1
    scheduler.tick(http, "2026-10-25")  # next day: allowed again
    assert calls.count(("POST", "/internal/briefings/send-due")) == 3


def test_each_tick_queues_then_sweeps_in_that_order(monkeypatch):
    _reset(monkeypatch, [])
    calls = []
    scheduler.tick(_http(calls), "2026-10-24")
    order = [p for _, p in calls if p.startswith("/internal/")]
    assert order == [
        "/internal/checkin-users",
        "/internal/reminders/fire-due",
        "/internal/medicines/tick",
        "/internal/checkins/tick",
        "/internal/deliveries/sweep",
        "/internal/briefings/send-due",
    ]


def test_a_failing_sweep_does_not_stop_the_briefing_or_the_opener(monkeypatch):
    _reset(monkeypatch, [1])
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        path = request.url.path
        if path == "/internal/deliveries/sweep":
            return httpx.Response(500)
        if path == "/internal/reminders/fire-due":
            return httpx.Response(200, json=[])
        if path == "/internal/medicines/tick":
            return httpx.Response(200, json={"reminded": [], "unconfirmed": []})
        if path == "/internal/checkins/tick":
            return httpx.Response(200, json={"asked": [], "followed_up": [], "closed": []})
        if path == "/internal/checkin-users":
            return httpx.Response(200, json=[])
        if path == "/internal/briefings/send-due":
            return httpx.Response(200, json={"sent": 1, "failed": 0, "skipped": 0})
        if path.startswith("/briefing/"):
            return httpx.Response(200, json={"text": "सुप्रभात"})
        return httpx.Response(200, json={"text": "आजी"})

    scheduler.tick(httpx.Client(transport=httpx.MockTransport(handler), base_url="http://x"), "2026-10-24")
    assert ("POST", "/internal/briefings/send-due") in calls and ("POST", "/opener/1") in calls


def test_the_log_never_claims_a_reminder_was_spoken(monkeypatch, caplog):
    _reset(monkeypatch, [])
    caplog.set_level("INFO", logger="scheduler")
    scheduler.tick(_http([]), "2026-10-24")
    text = " ".join(r.getMessage() for r in caplog.records).lower()
    assert "queued for delivery" in text and "spoken" not in text.replace("not spoken", "")


def test_dev_up_starts_the_scheduler_without_giving_it_secrets_it_does_not_need():
    """T8: without the scheduler nothing is ever queued, so the hand test would silently never speak."""
    import re
    from pathlib import Path

    script = (Path(__file__).resolve().parents[2] / "scripts" / "dev-up.ps1").read_text(encoding="utf-8")
    block = re.search(r'"scheduler"\s*=\s*@\{(.*?)"voice-agent"\s*=', script, re.S)
    assert block, "scripts/dev-up.ps1 has no scheduler entry"
    entry = "\n".join(line for line in block.group(1).splitlines() if not line.strip().startswith("#"))
    assert "scheduler.py" in entry
    for needed in ("CORE_API_URL", "CORE_API_KEY", "REASONING_URL", "ARJUN_TZ", "SCHEDULER_INTERVAL_SECONDS"):
        assert needed in entry
    for forbidden in ("LLM_API_KEY", "GNANI_API_KEY", "LIVEKIT_API_SECRET"):
        assert forbidden not in entry
    assert "OPENER_USER_IDS" in entry and "BRIEFING_USER_IDS" not in entry
    assert '"scheduler"' in script.split("ValidateSet(")[1].split(")")[0]


def test_each_tick_asks_reasoning_to_send_finished_conversation_summaries(monkeypatch):
    _reset(monkeypatch, [])
    calls = []
    scheduler.tick(_http(calls), "2026-10-24")
    assert ("POST", "/conversations/flush-idle") in calls
