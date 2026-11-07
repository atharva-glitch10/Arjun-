"""Family presence in the LiveKit room (pure).

While a family member is in the elder's room, Arjun stays quiet: he does not answer turns and does not
speak reminders or close the session, so the family can talk without a third voice. The elder page
shows a banner ("चंद्रकांत बोलत आहेत"); this module only decides silence.

The family joins with the identity "family" (see core_api/family_call.py), so no display name has to
travel here: the identity is the one stable marker.
"""

from __future__ import annotations

from safety_words import is_safety_phrase

FAMILY_IDENTITY = "family"


class FamilyPresence:
    def __init__(self) -> None:
        self._ids: set[str] = set()

    def joined(self, identity: str) -> None:
        if identity == FAMILY_IDENTITY:
            self._ids.add(identity)

    def left(self, identity: str) -> None:
        self._ids.discard(identity)

    def present(self) -> bool:
        return bool(self._ids)

    def quiet(self, speech_locked: bool) -> bool:
        """Same meaning as SessionState.quiet: may a proactive line be spoken right now?"""
        return speech_locked or self.present()

    @staticmethod
    def should_process(text: str) -> bool:
        """While family is present, only safety utterances reach reasoning."""
        return is_safety_phrase(text)
