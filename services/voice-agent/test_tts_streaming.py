"""The first SSE audio frames must reach LiveKit before synthesis finishes."""

import asyncio
from dataclasses import dataclass

from ttspipeline import PrefetchedFrames, prebuffer_ms
from turnlog import TurnLog


@dataclass
class Frame:
    number: int
    duration: float = 0.1


def test_fake_sse_chunks_reach_playback_before_stream_ends(monkeypatch):
    for name in ("GNANI_API_KEY", "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
        monkeypatch.setenv(name, "test")
    import agent

    ended = asyncio.Event()

    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def __aiter__(self):
            async def chunks():
                for number in range(4):
                    await asyncio.sleep(0.1)
                    yield type("Event", (), {"frame": Frame(number)})()
                ended.set()

            return chunks()

    class FakeSseTTS:
        def synthesize(self, _text):
            return Stream()

    async def check():
        prefetched = PrefetchedFrames(lambda: agent.tts_audio(FakeSseTTS(), "synthetic", prefetch=True))
        received = []
        async for frame in prefetched.frames():
            received.append(frame.number)
            if len(received) == 1:
                assert not ended.is_set()
                assert not prefetched.task.done()
        assert received == [0, 1, 2, 3]
        assert ended.is_set()

    asyncio.run(check())


def test_prebuffer_setting_is_bounded():
    assert [prebuffer_ms(value) for value in (None, "0", "200", "1001", "bad")] == [150, 0, 200, 150, 150]


def test_turnlog_reports_tts_chunk_and_frame_times(tmp_path):
    log = TurnLog("mr-IN", tmp_path / "turns.jsonl")
    log.final_transcript(100.0, "synthetic", "mr-IN")
    idx = log.reasoning_started("synthetic", 100.1)
    log.tts_event(idx, "t_request_start", 101.0)
    log.tts_event(idx, "t_first_chunk_received", 101.4)
    log.tts_event(idx, "t_first_frame_pushed", 101.6)
    log.tts_event(idx, "t_last_chunk", 102.0)
    log.speaking_for(idx, 101.5)
    log.agent_speaking(101.7)
    row = __import__("json").loads((tmp_path / "turns.jsonl").read_text(encoding="utf-8"))
    assert (row["tts_first_chunk_ms"], row["tts_first_frame_ms"]) == (400, 600)
    assert row["t_last_chunk"] == 102.0
