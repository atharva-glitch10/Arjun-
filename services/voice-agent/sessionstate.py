"""What the voice session is doing right now, as seen from the LiveKit events. Pure, so it is tested.

A reminder is only spoken, and an idle session only closed, when the session is QUIET: Arjun is listening,
the elder is not speaking, no spoken turn is being answered, and nothing else holds the speech lock.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class SessionState:
    def __init__(self) -> None:
        self.agent = "initializing"  # LiveKit agent state: initializing | listening | thinking | speaking
        self.user = "listening"  # LiveKit user state: listening | speaking | away
        self.speaking_count = 0  # how many times Arjun REALLY started speaking: proof audio was played
        self._turns = 0  # user turns being answered right now

    def on_agent_state(self, new: str) -> None:
        self.agent = new
        if new == "speaking":
            self.speaking_count += 1

    def on_user_state(self, new: str) -> None:
        self.user = new

    @asynccontextmanager
    async def turn(self) -> AsyncIterator[None]:
        """Wrap answering a spoken or tapped turn: while it runs the session is not quiet."""
        self._turns += 1
        try:
            yield
        finally:
            self._turns -= 1

    def quiet(self, speech_locked: bool) -> bool:
        return self.agent == "listening" and self.user != "speaking" and self._turns == 0 and not speech_locked
