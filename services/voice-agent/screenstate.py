"""The Ghar screen the elder app should show, published as participant attributes.

Attributes (not data messages) because they are STATE: a page that reloads or reconnects reads the
current screen at once, nothing arrives out of order or twice, and LiveKit already publishes the agent's
own state ("lk.agent.state": listening / thinking / speaking) the same way.
"""

import logging

from bridge import BridgeReply

logger = logging.getLogger("arjun.screen")

SCREEN = "arjun.screen"  # reply | story | confirm | saved | safety
TURN = "arjun.turn"  # increases with every spoken reply, so the app can tell a new reply from the same screen
REPLY = "arjun.reply"  # the exact line being spoken, for the reply / story / safety screens
MAX_REPLY_CHARS = 600


def attributes_for(reply: BridgeReply, turn: int) -> dict[str, str]:
    # Safety wins over every other screen: whatever reasoning labelled it, a safety-mode reply is "safety".
    screen = "safety" if reply.mode == "safety" else reply.screen
    return {SCREEN: screen, TURN: str(turn), REPLY: reply.text[:MAX_REPLY_CHARS]}


async def publish_screen(participant, reply: BridgeReply, turn: int) -> None:  # type: ignore[no-untyped-def]
    await participant.set_attributes(attributes_for(reply, turn))
