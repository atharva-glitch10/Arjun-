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
        if path.startswith("/briefing/"):
            return httpx.Response(200, json={"text": briefing_text})
        if path.startswith("/opener/"):
            return httpx.Response(200, json={"text": opener_text})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://x")


def _reset(monkeypatch, users):
    monkeypatch.setattr(scheduler, "CORE", "")
    monkeypatch.setattr(scheduler, "REASONING", "")
    monkeypatch.setattr(scheduler, "BRIEFING_USER_IDS", users)
    monkeypatch.setattr(scheduler, "OPENER_USER_IDS", users)
    scheduler._briefed_today.clear()
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
    assert calls.count(("GET", "/briefing/1")) == 1
    assert calls.count(("POST", "/opener/1")) == 1
    scheduler.tick(http, "2026-10-25")  # next day: allowed again
    assert calls.count(("GET", "/briefing/1")) == 2


def test_null_briefing_is_retried_later_same_day(monkeypatch):
    _reset(monkeypatch, [1])
    calls = []
    scheduler.tick(_http(calls, briefing_text=None, opener_text=None), "2026-10-24")
    scheduler.tick(_http(calls, briefing_text=None, opener_text=None), "2026-10-24")
    assert calls.count(("GET", "/briefing/1")) == 2  # None (before wake time) is not "done"
    assert calls.count(("POST", "/opener/1")) == 2
