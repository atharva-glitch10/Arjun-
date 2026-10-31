"""Per-user token bucket for /turn (same algorithm as core-api's; each service owns its copy on purpose:
services share HTTP contracts, not code)."""

import threading
import time
from collections.abc import Callable


class TokenBucket:
    def __init__(self, rate: float, burst: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.rate, self.burst, self.clock = rate, burst, clock
        self._state: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def take(self, key: str) -> float:
        """0.0 if allowed, else seconds until the next token."""
        now = self.clock()
        with self._lock:
            tokens, last = self._state.get(key, (float(self.burst), now))
            tokens = min(float(self.burst), tokens + (now - last) * self.rate)
            if tokens >= 1.0:
                self._state[key] = (tokens - 1.0, now)
                return 0.0
            self._state[key] = (tokens, now)
            return (1.0 - tokens) / self.rate if self.rate > 0 else float("inf")
