"""Regression: LiveKit 1.8.6 AgentSession.say() has no `tts=` argument. Passing it raised TypeError on every reply
(2026-11-07..08: Arjun answered on screen but never spoke). Check the real signature and every call site."""

import ast
import asyncio
import inspect
import pathlib

from livekit.agents.voice.agent_session import AgentSession


def _say_calls():
    tree = ast.parse(pathlib.Path(__file__).with_name("agent.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "say":
            yield node


def test_every_say_call_uses_only_supported_keywords():
    allowed = set(inspect.signature(AgentSession.say).parameters) - {"self", "text"}
    calls = list(_say_calls())
    assert calls, "expected session.say(...) calls in agent.py"
    for call in calls:
        used = {k.arg for k in call.keywords if k.arg}
        assert used <= allowed, f"line {call.lineno}: say() does not accept {sorted(used - allowed)}"


def test_tts_audio_yields_frames_from_the_chosen_tts(monkeypatch):
    for name in ("GNANI_API_KEY", "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
        monkeypatch.setenv(name, "test")
    import agent

    class Ev:
        def __init__(self, frame):
            self.frame = frame

    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def __aiter__(self):
            async def gen():
                for f in ("f1", "f2"):
                    yield Ev(f)
            return gen()

    class FakeTTS:
        def __init__(self):
            self.text = None

        def synthesize(self, text):
            self.text = text
            return Stream()

    tts = FakeTTS()

    async def collect():
        return [f async for f in agent.tts_audio(tts, "नमस्कार")]

    assert asyncio.run(collect()) == ["f1", "f2"] and tts.text == "नमस्कार"
