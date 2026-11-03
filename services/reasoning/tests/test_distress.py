import pytest
from reasoning_svc.distress import is_distress

POSITIVE = [
    "mala jagaychi iccha nahi",
    "मला जगायची इच्छा नाही",
    "mala marayche aahe",
    "mala koni marto",
    "मला भीती वाटतेय",
    "I want to die",
    "i am scared",
    "no reason to live",
    "mujhe dar lag raha hai",
    "जीने का मन नहीं",
    "आत्महत्या",
    # spelling / inflection variants (written by the same author as the patterns: not independent)
    "मरना चाहता हूं", "मरना चाहता हूँ", "मला मरायचे आहे", "मला मरायचंय", "मला मरायचं आहे.",
    "मला जगायचं नाही", "मला जगावेसे वाटत नाही", "मी जगायला नको",
    "mala jagaycha nahi", "mi marun jain", "main mar jaana chahta hoon", "mujhe jeena nahi hai",
    "I don't want to live", "i dont want to live", "i want to end it all", "no one would miss me",
    "I can't go on",
]
NEGATIVE = [
    "udya doctor la jaycha aahe remind kar",
    "mala bhook lagli aahe",
    "aaj jevan zala",
    "what is the time",
    "माझ्या नातवाला भेटायचंय",
    "mi gavala jat hoto tevha shala hoti",
    "मला मरायला वेळ नाही",
    "mala marathi shikaychi aahe",
    "i do not want to eat now",
]


@pytest.mark.parametrize("text", POSITIVE)
def test_distress_detected(text):
    assert is_distress(text)


@pytest.mark.parametrize("text", NEGATIVE)
def test_no_false_distress(text):
    assert not is_distress(text)


def test_distress_overrides_pending_and_never_executes(engine, core_http, uid):
    engine.handle(uid, "udya 19:30 vajta doctor remind kar")  # leaves a pending action
    assert core_http.get(f"/users/{uid}/actions/pending").json() is not None
    res = engine.handle(uid, "mala jagaychi iccha nahi")
    assert res.mode == "safety" and res.intent == "DISTRESS"
    assert "मुलाला फोन लाव" in res.reply  # consent off: no claim that the family was told
    assert core_http.get(f"/users/{uid}/actions/pending").json() is None
    engine.handle(uid, "ho")  # stray yes after distress must not create anything
    assert core_http.get(f"/users/{uid}/reminders").json() == []


def test_distress_caregiver_alert_requires_consent(engine, core_http, uid):
    engine.handle(uid, "I want to die")
    assert core_http.get(f"/users/{uid}/notifications").json() == []
    core_http.patch(f"/users/{uid}", json={"consent_distress_alert": True})
    engine.handle(uid, "I want to die")
    assert len(core_http.get(f"/users/{uid}/notifications").json()) == 1


def test_distress_reply_makes_no_feeling_or_diagnosis_claims(engine, uid):
    reply = engine.handle(uid, "I want to die").reply.lower()
    for bad in ("depress", "diagnos", "i feel", "i am sad"):
        assert bad not in reply


def test_distress_reply_survives_core_api_failure(uid):
    """If core-api is unreachable the gentle reply must still be spoken (boundary 6)."""
    import httpx
    from reasoning_svc.core_client import CoreClient
    from reasoning_svc.turn import TurnEngine

    def down(request):
        raise httpx.ConnectError("core-api down", request=request)

    http = httpx.Client(transport=httpx.MockTransport(down), base_url="http://core")
    res = TurnEngine(CoreClient(http), evon=None).handle(uid, "I want to die")
    assert res.mode == "safety" and res.intent == "DISTRESS"
    assert "कळवलं" not in res.reply  # nothing was alerted: the reply must not claim it
    assert "मुलाला फोन लाव" in res.reply


# ---- the family the safety line names (2026-11-03) ---------------------------------------------------------
def _son(core_http, uid, name="चंद्रकांत", relation="मुलगा"):
    core_http.post(f"/users/{uid}/contacts", json={"name": name, "relation": relation, "phone": "00000 00003"})


def test_the_son_is_named_and_a_consented_alert_is_confirmed(engine, core_http, uid):
    core_http.patch(f"/users/{uid}", json={"consent_distress_alert": True})
    _son(core_http, uid)
    res = engine.handle(uid, "मला त्रास होतोय तू माझ्या मुलाला कळवलंय का")
    assert res.mode == "safety" and res.intent == "DISTRESS"
    assert "चंद्रकांतला" in res.reply and "कळवलं" in res.reply
    assert "मुलाला फोन लाव" not in res.reply


def test_consent_off_never_claims_the_family_was_told(engine, core_http, uid):
    _son(core_http, uid)
    res = engine.handle(uid, "मला त्रास होतोय")
    assert res.mode == "safety" and res.intent == "DISTRESS"
    assert "कळवलं" not in res.reply
    assert "मुलाला फोन लाव" in res.reply


def test_a_doctor_only_contact_falls_back_to_your_family(engine, core_http, uid):
    core_http.patch(f"/users/{uid}", json={"consent_distress_alert": True})
    _son(core_http, uid, name="डॉ. कुलकर्णी", relation="डॉक्टर")
    res = engine.handle(uid, "मला त्रास होतोय")
    assert "तुमच्या घरच्यांना" in res.reply and "कळवलं" in res.reply
    assert "कुलकर्णी" not in res.reply  # a doctor is never named as the family


def test_the_other_family_member_is_used_when_there_is_no_son(engine, core_http, uid):
    core_http.patch(f"/users/{uid}", json={"consent_distress_alert": True})
    _son(core_http, uid, name="डॉ. कुलकर्णी", relation="डॉक्टर")
    _son(core_http, uid, name="नेहा", relation="नात")
    res = engine.handle(uid, "मला त्रास होतोय")
    assert "नेहाला" in res.reply and "कुलकर्णी" not in res.reply
