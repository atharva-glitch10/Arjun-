"""Bounded first-sentence prefetch and a small audio prebuffer."""

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

logger = logging.getLogger("arjun.tts")


class TtsTiming:
    def __init__(self, turn: int | None = None, on_event: Callable[[str, float], None] | None = None) -> None:
        self.turn, self.on_event = turn, on_event
        self.request_start: float | None = None
        self.first_chunk: float | None = None
        self.first_frame: float | None = None
        self.last_chunk: float | None = None
        self.active_concurrent = 0

    def _record(self, name: str, when: float) -> None:
        if self.on_event is not None:
            self.on_event(name, when)

    def start(self, active_concurrent: int) -> None:
        self.request_start = time.time()
        self.first_chunk = self.first_frame = self.last_chunk = None
        self.active_concurrent = active_concurrent
        self._record("t_request_start", self.request_start)

    def chunk(self) -> None:
        now = time.time()
        if self.first_chunk is None:
            self.first_chunk = now
            self._record("t_first_chunk_received", now)
        self.last_chunk = now
        self._record("t_last_chunk", now)

    def frame(self) -> None:
        if self.first_frame is None:
            self.first_frame = time.time()
            self._record("t_first_frame_pushed", self.first_frame)
            self.log("first_frame")

    def log(self, event: str) -> None:
        logger.info(
            "tts request event=%s turn=%s t_request_start=%s t_first_chunk_received=%s "
            "t_first_frame_pushed=%s t_last_chunk=%s active_concurrent=%s",
            event, self.turn, self.request_start, self.first_chunk, self.first_frame,
            self.last_chunk, self.active_concurrent,
        )


def prebuffer_ms(value: str | None) -> int:
    try:
        amount = int(value or "150")
    except ValueError:
        return 150
    return amount if 0 <= amount <= 1000 else 150


async def prebuffer(frames: AsyncIterator[Any], milliseconds: int) -> AsyncIterator[Any]:
    buffered: list[Any] = []
    duration_ms = 0.0
    async for frame in frames:
        buffered.append(frame)
        duration = getattr(frame, "duration", None)
        if duration is None:  # test doubles or a provider without duration: do not hold audio
            duration_ms = milliseconds
        else:
            duration_ms += duration * 1000
        if duration_ms >= milliseconds:
            for ready in buffered:
                yield ready
            buffered.clear()
    for ready in buffered:
        yield ready


class PrefetchedFrames:
    """Let synthesis proceed while reasoning finishes, then hand frames over as they arrive."""

    def __init__(self, source: Callable[[], AsyncIterator[Any]]) -> None:
        self._queue: asyncio.Queue[Any | None] = asyncio.Queue(maxsize=32)
        self.task = asyncio.create_task(self._produce(source))

    async def _produce(self, source: Callable[[], AsyncIterator[Any]]) -> None:
        try:
            async for frame in source():
                await self._queue.put(frame)
            await self._queue.put(None)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._queue.put(None)
            raise

    async def frames(self) -> AsyncIterator[Any]:
        try:
            while (frame := await self._queue.get()) is not None:
                yield frame
            await self.task  # propagate synthesis failures to the ordinary voice fallback
        finally:
            if not self.task.done():
                self.task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self.task

    def cancel(self) -> None:
        self.task.cancel()
