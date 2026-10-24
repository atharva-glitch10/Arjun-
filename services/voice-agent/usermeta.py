"""Which user a voice session serves: the dispatch metadata set by core-api's /livekit/token.

The token carries the browser's user id as metadata on the agent dispatch, so the app and the agent can never
disagree (before this, the agent always used ARJUN_USER_ID while the browser could be on another user).
ARJUN_USER_ID stays as the fallback for rooms dispatched without metadata (Console, the playground).
"""

import json


def user_id_from_metadata(metadata: str | None, default: int) -> int:
    try:
        value = json.loads(metadata or "")["user_id"]
    except (ValueError, KeyError, TypeError):
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    return value if isinstance(value, int) and value > 0 else default
