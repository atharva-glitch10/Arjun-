"""Emergency escalation from the voice session (team decision 2026-11-08).

After Arjun speaks the FIXED emergency template (reasoning, intent EMERGENCY): phone the family at once, ask her
"are you okay?", wait ARJUN_EMERGENCY_WAIT_S (10 s) for any speech, and if she says nothing, phone the help number
the family saved. core-api places the calls (Twilio, only when CALLS_ENABLED=1) and records the real outcome. Arjun
never dials 112 by itself and never says help is coming: only what was actually attempted.
"""

import os
from typing import Any

import httpx

WAIT_S = float(os.environ.get("ARJUN_EMERGENCY_WAIT_S", "10") or 10)
ASK_OK = "तुम्ही ठीक आहात का? काहीतरी बोला."
SAID_HELP_CALLED = "तुम्ही उत्तर दिलं नाही, म्हणून मी मदतीसाठी फोन लावला आहे. घरच्यांनाही कळवलं आहे. शक्य असेल तर 112 ला फोन करा."
SAID_NO_CALL = "तुम्ही उत्तर दिलं नाही. घरच्यांना कळवलं आहे. शक्य असेल तर 112 ला फोन करा."


def is_emergency(reply: Any) -> bool:
    return (getattr(reply, "intent", "") or "").strip().upper() == "EMERGENCY"


def escalate(user_id: int, stage: str) -> dict[str, Any]:
    """POST the stage to core-api. Never raises: a failure is reported as 0 calls placed."""
    base = os.environ.get("CORE_API_URL", "http://127.0.0.1:8000").rstrip("/")
    headers = {"X-API-Key": os.environ["CORE_API_KEY"]} if os.environ.get("CORE_API_KEY") else {}
    try:
        res = httpx.post(f"{base}/internal/users/{user_id}/emergency/escalate", json={"stage": stage},
                         headers=headers, timeout=20.0)
        res.raise_for_status()
        return res.json()
    except (httpx.HTTPError, ValueError) as exc:
        return {"stage": stage, "placed": 0, "error": type(exc).__name__}
