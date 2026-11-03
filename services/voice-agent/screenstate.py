"""The Ghar screen the elder app should show, published as participant attributes.

Attributes (not data messages) because they are STATE: a page that reloads or reconnects reads the
current screen at once, nothing arrives out of order or twice, and LiveKit already publishes the agent's
own state ("lk.agent.state": listening / thinking / speaking) the same way.
"""

import json
import logging

from bridge import BridgeReply

logger = logging.getLogger("arjun.screen")

SCREEN = "arjun.screen"  # reply | story | confirm | saved | safety
TURN = "arjun.turn"  # increases with every spoken reply, so the app can tell a new reply from the same screen
REPLY = "arjun.reply"  # the exact line being spoken, for the reply / story / safety screens
ITEM = "arjun.item"  # reminder:<id> | dose:<id> for a delivered reminder / medicine prompt, else empty
ACTION = "arjun.action"  # JSON {type: open|control, kind, value, title, video_id, turn} for the page to perform; "" = none
THINKING = "arjun.thinking"  # "1" while reasoning works out the answer: the elder screen shows "विचार करतोय…"
MAX_REPLY_CHARS = 600
_ACTION_KEYS = ("type", "kind", "value", "title", "video_id", "contact_id", "command", "query", "label")


def attributes_for(reply: BridgeReply, turn: int) -> dict[str, str]:
    # Safety wins over every other screen: whatever reasoning labelled it, a safety-mode reply is "safety".
    screen = "safety" if reply.mode == "safety" else reply.screen
    return {
        SCREEN: screen, TURN: str(turn), REPLY: reply.text[:MAX_REPLY_CHARS], ITEM: "", THINKING: "0",
        ACTION: action_json(reply, turn),
    }


def action_json(reply: BridgeReply, turn: int) -> str:
    """The action as one JSON attribute, tagged with the turn number so the page performs it exactly once. Never on a
    safety reply: nothing opens in the middle of an emergency. "" clears the previous action."""
    action = reply.action or {}
    if reply.mode == "safety" or action.get("type") not in ("open", "control"):
        return ""
    payload = {k: str(action[k]) for k in _ACTION_KEYS if action.get(k) not in (None, "")}
    return json.dumps({**payload, "turn": turn}, ensure_ascii=False)


def delivery_attributes(item: dict, turn: int) -> dict[str, str]:  # type: ignore[type-arg]
    """A queued reminder / medicine prompt: the screen to show and which SQL item it is (the app reads the card from SQL)."""
    return {SCREEN: item["screen"], TURN: str(turn), REPLY: item["text"][:MAX_REPLY_CHARS], ITEM: item["item"]}


def closed_attributes(turn: int) -> dict[str, str]:
    """The session ended on purpose (idle): tells the app this is a normal end, not a dropped connection."""
    return {SCREEN: "closed", TURN: str(turn), REPLY: "", ITEM: ""}


async def publish_screen(participant, reply: BridgeReply, turn: int) -> None:  # type: ignore[no-untyped-def]
    await participant.set_attributes(attributes_for(reply, turn))


async def publish_delivery(participant, item: dict, turn: int) -> None:  # type: ignore[no-untyped-def,type-arg]
    await participant.set_attributes(delivery_attributes(item, turn))


async def publish_closed(participant, turn: int) -> None:  # type: ignore[no-untyped-def]
    await participant.set_attributes(closed_attributes(turn))


async def publish_thinking(participant, on: bool) -> None:  # type: ignore[no-untyped-def]
    await participant.set_attributes({THINKING: "1" if on else "0"})
