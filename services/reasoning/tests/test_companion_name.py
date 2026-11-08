from reasoning_svc.turn import TurnResult, companion_name, rename_companion


def test_default_and_family_set_name():
    assert companion_name({}) == "Arjun"
    assert companion_name({"speech_style": {"companion_name": "  "}}) == "Arjun"
    assert companion_name({"speech_style": {"companion_name": "गुड्डू"}}) == "गुड्डू"
    assert rename_companion("मी अर्जुन आहे", "गुड्डू") == "मी गुड्डू आहे"
    assert rename_companion("I am Arjun", "Arjun") == "I am Arjun"


def test_renamed_companion_says_its_name(engine, core_http, uid):
    core_http.patch(f"/users/{uid}", json={"speech_style": {"rate": "normal", "volume": "normal", "simple": False,
                                                             "companion_name": "गुड्डू"}})
    res = engine.handle(uid, "तू माणूस आहेस का?")
    assert "गुड्डू" in res.reply and "अर्जुन" not in res.reply
    engine.handle(uid, "नेहमीसारखं बोल")
    assert core_http.get(f"/users/{uid}").json()["speech_style"]["companion_name"] == "गुड्डू"


def test_same_chat_line_is_not_repeated(engine, uid):
    r = TurnResult("बरं.", "CHAT", "companion", "mr")
    first = engine._vary_repeat(uid, r)
    second = engine._vary_repeat(uid, TurnResult("बरं.", "CHAT", "companion", "mr"))
    assert first.reply == "बरं." and second.reply != "बरं."
    safety = engine._vary_repeat(uid, TurnResult("112 वर फोन करा.", "EMERGENCY", "safety", "mr"))
    again = engine._vary_repeat(uid, TurnResult("112 वर फोन करा.", "EMERGENCY", "safety", "mr"))
    assert safety.reply == again.reply == "112 वर फोन करा."
