from reasoning_svc import main as reasoning_main


def _add_contact(client, uid, name, relation):
    return client.post(f"/users/{uid}/contacts", json={"name": name, "relation": relation, "phone": "00000 00001"}).json()


def test_video_call_named_contact_and_family_fallback_skip_doctor(auto, core_http, uid):
    _add_contact(core_http, uid, "डॉ. कुलकर्णी", "डॉक्टर")
    son = _add_contact(core_http, uid, "चंद्रकांत", "मुलगा")
    other = _add_contact(core_http, uid, "विमल", "बहीण")
    for phrase in ("व्हिडिओ कॉल कर", "व्हिडिओ कॉल लाव", "मुलाला व्हिडिओवर बोलव", "video call kar"):
        result = auto.handle(uid, phrase)
        assert result.intent == "VIDEO_CALL"
        assert result.action["value"] == str(son["id"])
    named = auto.handle(uid, "चंद्रकांतला व्हिडिओ कॉल लाव")
    assert named.action["value"] == str(son["id"])
    assert "थांबा" in named.reply and "लागला" not in named.reply
    assert auto.handle(uid, "मुलाला फोन लाव").intent == "CALL_FAMILY_REMINDER"
    assert other["id"] != son["id"]


def test_video_call_safety_wins_and_stop_clears_media_choice(auto, core_http, uid, monkeypatch):
    _add_contact(core_http, uid, "चंद्रकांत", "मुलगा")
    result = auto.handle(uid, "छातीत दुखतंय, व्हिडिओ कॉल लाव")
    assert result.mode == "safety"
    auto._media_choice[uid] = object()
    auto._media_ask[uid] = 1.0
    auto.video_call_stopped(uid)
    assert uid not in auto._media_choice
    assert uid not in auto._media_ask


def test_missed_call_marker_gets_exact_fixed_reply(auto, uid):
    result = auto.handle(uid, "[video_call_missed] चंद्रकांत")
    assert result.reply == "चंद्रकांतनी उचलला नाही, मी निरोप ठेवला आहे."
    assert result.intent == "VIDEO_CALL_MISSED"


def test_media_call_stopped_endpoint_clears_engine_state(monkeypatch):
    seen = []

    class Engine:
        def video_call_stopped(self, user_id):
            seen.append(user_id)

    monkeypatch.setattr(reasoning_main, "_engine", Engine())
    result = reasoning_main.media_call_stopped(reasoning_main.MediaStoppedIn(user_id=42))
    assert result == {"ok": True}
    assert seen == [42]
