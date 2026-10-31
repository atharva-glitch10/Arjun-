"""Token-bucket rate limiting, shared by core-api (HTTP middleware) and reasoning (per-user /turn).

Why: one runaway client (a dashboard tab stuck in a loop, a misbehaving script) must not starve the voice path.
A bucket holds `burst` tokens and refills at `rate` per second; each request takes one; an empty bucket answers
429 with Retry-After. In memory, per process: good for one instance; several replicas would need a shared store.
"""

from __future__ import annotations

import math
import os
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any


class TokenBucket:
    def __init__(self, rate: float, burst: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.rate, self.burst, self.clock = rate, burst, clock
        self._state: dict[str, tuple[float, float]] = {}  # key -> (tokens, last time)
        self._lock = threading.Lock()

    def take(self, key: str) -> float:
        """0.0 if allowed, else the seconds to wait before the next token."""
        now = self.clock()
        with self._lock:
            tokens, last = self._state.get(key, (float(self.burst), now))
            tokens = min(float(self.burst), tokens + (now - last) * self.rate)
            if tokens >= 1.0:
                self._state[key] = (tokens - 1.0, now)
                return 0.0
            self._state[key] = (tokens, now)
            return (1.0 - tokens) / self.rate if self.rate > 0 else math.inf
            # (old keys are cheap; a household has a handful of clients)


Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


class RateLimitMiddleware:
    """Pure ASGI middleware: one bucket per client address. /health and WebSockets are never limited."""

    def __init__(self, app: Callable[..., Awaitable[None]], bucket: TokenBucket | None = None) -> None:
        self.app = app
        self.bucket = bucket or TokenBucket(
            float(os.environ.get("CORE_RATE_PER_S", "30")), int(os.environ.get("CORE_RATE_BURST", "60"))
        )
        # The test suites make hundreds of fast calls from one client; they test the limiter on its own.
        self.enabled = os.environ.get("CORE_RATE_LIMIT", "0" if os.environ.get("ARJUN_TESTING") == "1" else "1") == "1"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.enabled or scope["type"] != "http" or scope.get("path") == "/health":
            await self.app(scope, receive, send)
            return
        client = scope.get("client") or ("unknown", 0)
        wait = self.bucket.take(str(client[0]))
        if wait == 0.0:
            await self.app(scope, receive, send)
            return
        retry = str(max(1, math.ceil(wait)))
        await send({
            "type": "http.response.start",
            "status": 429,
            "headers": [(b"content-type", b"application/json"), (b"retry-after", retry.encode())],
        })
        await send({"type": "http.response.body", "body": b'{"detail":"too many requests"}'})
