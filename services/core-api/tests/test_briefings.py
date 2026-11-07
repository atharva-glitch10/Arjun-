from datetime import date, datetime

import httpx
from core_api import briefings as svc
from core_api import models as m
from core_api import telegram
from core_api.db import get_db


def _set_day_data(client, uid, *, consent=False):
    client.patch(f"/users/{uid}", json={"daily_checkins": True, "consent_distress_alert": consent})
    with next(client.app.dependency_overrides[get_db]()) as db:
        db.add(m.Medicine(user_id=uid, name="Demo tablet", dose="one", time="08:00"))
        db.flush()
        med = db.query(m.Medicine).filter_by(user_id=uid).one()
        db.add(m.MedicineDose(
            user_id=uid, medicine_id=med.id, for_date=date(2026, 10, 6),
            due_at=datetime(2026, 10, 6, 8), status="taken",
        ))
        db.add(m.BpReading(user_id=uid, systolic=120, diastolic=80, measured_at=datetime(2026, 10, 6, 8)))
        db.add(m.Checkin(user_id=uid, kind="breakfast", for_date=date(2026, 10, 6), due_at=datetime(2026, 10, 6, 8), status="done"))
        db.commit()


def test_build_briefing_uses_daily_data_and_hides_mood_summary_without_consent(client, uid):
    _set_day_data(client, uid)
    with next(client.app.dependency_overrides[get_db]()) as db:
        db.add(m.Wellbeing(
            user_id=uid, kind="conversation", mood="calm", summary="SYNTHETIC_PARAPHRASE",
            created_at=datetime(2026, 10, 6, 8),
        ))
        db.commit()
        text = svc.build_briefing(uid, date(2026, 10, 6), db)
    assert "1 औषधांच्या नोंदी" in text
    assert "120/80" in text
    assert "नाश्ता" in text
    assert "SYNTHETIC_PARAPHRASE" not in text and "शांत" not in text
    assert len([s for s in text.split(".") if s.strip()]) == 3


def test_build_briefing_includes_only_consented_paraphrase_and_mood(client, uid):
    _set_day_data(client, uid, consent=True)
    with next(client.app.dependency_overrides[get_db]()) as db:
        db.add(m.Wellbeing(
            user_id=uid, kind="conversation", mood="calm", summary="बागेची आठवण सांगितली",
            created_at=datetime(2026, 10, 6, 8),
        ))
        db.commit()
        text = svc.build_briefing(uid, date(2026, 10, 6), db)
    assert "मनःस्थिती: शांत" in text
    assert "आजचा ठळक भाग: बागेची आठवण सांगितली." in text
    assert len([s for s in text.split(".") if s.strip()]) == 5


def test_scheduled_briefing_waits_until_configured_time(client, uid, monkeypatch):
    client.patch(f"/users/{uid}", json={"daily_checkins": True})
    monkeypatch.setenv("BRIEFING_TIME", "20:30")
    r = client.post("/internal/briefings/send-due")
    assert r.status_code == 200
    assert r.json() == {"sent": 0, "failed": 0, "skipped": 0}


def test_manual_briefing_sends_voice_once_and_force_can_resend(client, uid, monkeypatch):
    _set_day_data(client, uid)
    monkeypatch.setattr(svc, "VOICE_URL", "http://127.0.0.1:8002/synthesize")
    calls = []
    monkeypatch.setattr(svc.telegram, "send_voice", lambda audio, caption: calls.append((audio, caption)) or True)
    monkeypatch.setattr(svc.httpx, "post", lambda *a, **kw: httpx.Response(200, content=b"OggS-demo"))
    first = client.post(f"/users/{uid}/briefing/send", json={"force": True})
    second = client.post(f"/users/{uid}/briefing/send", json={"force": False})
    third = client.post(f"/users/{uid}/briefing/send", json={"force": True})
    assert first.json() == third.json() == {"status": "sent"}
    assert second.json() == {"status": "skipped"}
    assert calls == [(b"OggS-demo", "आजचा सारांश")] * 2
    notes = client.get(f"/users/{uid}/notifications").json()
    assert [n["kind"] for n in notes].count("briefing_sent") == 2
    assert all("OggS" not in n["body"] for n in notes)


def test_failed_voice_or_telegram_delivery_is_recorded_honestly(client, uid, monkeypatch):
    _set_day_data(client, uid)
    monkeypatch.setattr(svc, "VOICE_URL", "http://127.0.0.1:8002/synthesize")
    monkeypatch.setattr(svc.httpx, "post", lambda *a, **kw: httpx.Response(503))
    r = client.post(f"/users/{uid}/briefing/send", json={"force": True})
    assert r.json() == {"status": "failed"}
    assert client.get(f"/users/{uid}/notifications").json()[0]["kind"] == "briefing_failed"


def test_telegram_voice_uses_send_voice_with_caption_without_logging_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ENABLED", "1")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "synthetic-test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    seen = {}

    class Result:
        status_code = 200

        @staticmethod
        def json():
            return {"ok": True}

    def post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return Result()

    monkeypatch.setattr(telegram.httpx, "post", post)
    assert telegram.send_voice(b"OggSopus", "आजचा सारांश")
    assert seen["url"].endswith("/sendVoice")
    assert seen["data"] == {"chat_id": "12345", "caption": "आजचा सारांश"}
    assert seen["files"]["voice"] == ("briefing.ogg", b"OggSopus", "audio/ogg")


def test_internal_sweep_only_sends_opted_in_users_after_time(client, uid, monkeypatch):
    _set_day_data(client, uid)
    monkeypatch.setenv("BRIEFING_TIME", "08:00")
    monkeypatch.setattr(svc, "VOICE_URL", "http://127.0.0.1:8002/synthesize")
    monkeypatch.setattr(svc.httpx, "post", lambda *a, **kw: httpx.Response(503))
    r = client.post("/internal/briefings/send-due")
    assert r.json() == {"sent": 0, "failed": 1, "skipped": 0}
    r = client.post("/internal/briefings/send-due")
    assert r.json() == {"sent": 0, "failed": 0, "skipped": 1}
