"""Which user a voice session serves: the dispatch metadata set by core-api's /livekit/token.

The token carries the browser's user id as metadata on the agent dispatch, so the app and the agent can never
disagree (before this, the agent always used ARJUN_USER_ID while the browser could be on another user).
ARJUN_USER_ID stays as the fallback for rooms dispatched without metadata (Console, the playground).
"""

import json

_LANGS = frozenset({"mr", "hi", "en", "bn", "gu", "kn", "ml", "pa", "ta", "te", "or"})


def language_from_metadata(metadata: str | None) -> str | None:
    """The language the elder screen was set to when the token was issued ("hi"), or None."""
    try:
        value = json.loads(metadata or "").get("language")
    except (ValueError, AttributeError, TypeError):
        return None
    return value if isinstance(value, str) and value in _LANGS else None


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
