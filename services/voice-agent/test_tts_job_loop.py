"""Gnani's pooled HTTP session must belong to the loop synthesizing speech."""

import asyncio


def test_tts_synthesizes_in_job_thread_loop(monkeypatch):
    for name in ("GNANI_API_KEY", "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
        monkeypatch.setenv(name, "test")
    import agent

    class FakeStream:
        def __init__(self, plugin):
            self.plugin = plugin

        async def collect(self):
            session = self.plugin._session
            if asyncio.current_task(loop=session._loop) is None:
                raise RuntimeError("Timeout context manager should be used inside a task")
            return ["spoken audio"]

    class FakeTTS:
        def __init__(self, **_kwargs):
            self._session = None

        def synthesize(self, _text):
            return FakeStream(self)

    monkeypatch.setitem(agent.TTS, "method", "sse")
    monkeypatch.setattr(agent, "SseTimbre", FakeTTS)

    async def job():
        plugin = agent.make_tts("model", "voice", "hi-IN")
        try:
            assert await plugin.synthesize("hello").collect() == ["spoken audio"]
            return plugin
        finally:
            await agent.close_tts_session()

    async def main():
        first = agent.make_tts("model", "voice", "hi-IN")
        try:
            assert await first.synthesize("hello").collect() == ["spoken audio"]
            second = await asyncio.to_thread(lambda: asyncio.run(job()))
            assert first is not second
        finally:
            await agent.close_tts_session()

    asyncio.run(main())
