def _agent(monkeypatch):
    for name in ("GNANI_API_KEY", "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
        monkeypatch.setenv(name, "test")
    import agent

    return agent


def test_marathi_elder_also_gets_hindi_and_english(monkeypatch):
    monkeypatch.delenv("GNANI_STT_LANGUAGE_HINTS", raising=False)
    a = _agent(monkeypatch)
    assert a.prisma_language_hints(["mr"]) == ["mr-IN", "hi-IN", "en-IN"]
    assert a.prisma_language_hints(["ta", "hi"]) == ["ta-IN", "hi-IN", "en-IN"]
    assert len(a.prisma_language_hints(["mr", "ta", "kn", "te"])) == 4


def test_override(monkeypatch):
    a = _agent(monkeypatch)
    monkeypatch.setenv("GNANI_STT_LANGUAGE_HINTS", "auto")
    assert a.prisma_language_hints(["mr"]) == []  # indic-auto
    monkeypatch.setenv("GNANI_STT_LANGUAGE_HINTS", "mr-IN,ta-IN")
    assert a.prisma_language_hints(["mr"]) == ["mr-IN", "ta-IN"]
