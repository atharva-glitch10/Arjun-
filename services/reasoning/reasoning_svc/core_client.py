"""Thin HTTP client for core-api. All state lives there; reasoning only proposes."""

from typing import Any

import httpx

from . import config


class CoreError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"core-api {status}: {detail}")
        self.status = status
        self.detail = detail


class CoreClient:
    def __init__(self, http: httpx.Client | None = None) -> None:
        headers = {"X-API-Key": config.CORE_API_KEY} if config.CORE_API_KEY else {}
        self.http = http or httpx.Client(base_url=config.CORE_API_URL, headers=headers, timeout=10.0)

    def _req(self, method: str, path: str, **kw: Any) -> Any:
        r = self.http.request(method, path, **kw)
        if r.status_code >= 400:
            try:
                detail = str(r.json().get("detail", r.text))
            except ValueError:
                detail = r.text
            raise CoreError(r.status_code, detail)
        return r.json() if r.content else None

    def user(self, uid: int) -> dict[str, Any]:
        return self._req("GET", f"/users/{uid}")  # type: ignore[no-any-return]

    def contacts(self, uid: int) -> list[dict[str, Any]]:
        return self._req("GET", f"/users/{uid}/contacts")  # type: ignore[no-any-return]

    def today(self, uid: int) -> list[dict[str, Any]]:
        return self._req("GET", f"/users/{uid}/reminders/today")  # type: ignore[no-any-return]

    def next_appointment(self, uid: int) -> dict[str, Any] | None:
        return self._req("GET", f"/users/{uid}/appointments/next")  # type: ignore[no-any-return]

    def day(self, uid: int, on: str | None = None) -> dict[str, Any]:
        params = {"on": on} if on else None  # ISO date; omitted means today
        return self._req("GET", f"/users/{uid}/day", params=params)  # type: ignore[no-any-return]

    def due_medicines(self, uid: int) -> dict[str, Any]:
        return self._req("GET", f"/users/{uid}/medicines/due")  # type: ignore[no-any-return]

    def pending(self, uid: int) -> dict[str, Any] | None:
        return self._req("GET", f"/users/{uid}/actions/pending")  # type: ignore[no-any-return]

    def propose(self, uid: int, action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = {"action_type": action_type, "payload": payload}
        return self._req("POST", f"/users/{uid}/actions/propose", json=body)  # type: ignore[no-any-return]

    def confirm(self, uid: int, action_id: int) -> dict[str, Any]:
        return self._req("POST", f"/users/{uid}/actions/{action_id}/confirm")  # type: ignore[no-any-return]

    def reject(self, uid: int, action_id: int, answered_no: bool = False) -> dict[str, Any]:
        """answered_no=True only when the elder SAID no (a medicine "taken?" then counts as not taken)."""
        params = {"answer": "no"} if answered_no else None
        return self._req("POST", f"/users/{uid}/actions/{action_id}/reject", params=params)  # type: ignore[no-any-return]

    # ---- T8 delivery queue (core-api decides; reasoning only renders the fixed wording) ----
    def delivery_next(self, uid: int) -> dict[str, Any] | None:
        return self._req("GET", f"/users/{uid}/deliveries/next")  # type: ignore[no-any-return]

    def deliveries_waiting(self, uid: int) -> int:
        return int(self._req("GET", f"/users/{uid}/deliveries/waiting")["queued"])

    def open_checkin(self, uid: int) -> dict[str, Any] | None:
        """The one meal prompt still waiting for an answer; `heard` says a session really spoke it."""
        return self._req("GET", f"/users/{uid}/checkins/open")  # type: ignore[no-any-return]

    def answer_checkin(self, uid: int, checkin_id: int, answer: str) -> dict[str, Any]:
        return self._req(
            "POST", f"/users/{uid}/checkins/{checkin_id}/answer", json={"answer": answer}
        )  # type: ignore[no-any-return]

    def add_bp_reading(self, uid: int, systolic: int, diastolic: int) -> dict[str, Any]:
        """Raw numbers only; the reply repeats them back and never judges them (boundary 7)."""
        body = {"systolic": systolic, "diastolic": diastolic, "source": "voice"}
        return self._req("POST", f"/users/{uid}/bp-readings", json=body)  # type: ignore[no-any-return]

    def delivery_claim(self, uid: int, did: int, session: str) -> dict[str, Any]:
        return self._req("POST", f"/users/{uid}/deliveries/{did}/claim", json={"session": session})  # type: ignore[no-any-return]

    def delivery_spoken(self, uid: int, did: int, session: str) -> dict[str, Any]:
        return self._req("POST", f"/users/{uid}/deliveries/{did}/spoken", json={"session": session})  # type: ignore[no-any-return]

    def delivery_release(self, uid: int, did: int, session: str, reason: str) -> dict[str, Any]:
        body = {"session": session, "reason": reason}
        return self._req("POST", f"/users/{uid}/deliveries/{did}/release", json=body)  # type: ignore[no-any-return]

    def distress(self, uid: int, kind: str = "distress") -> dict[str, Any]:
        """kind="emergency" ALWAYS alerts the family; "distress" only with the user's consent."""
        return self._req("POST", f"/users/{uid}/distress", params={"kind": kind})  # type: ignore[no-any-return]

    def decline(self, uid: int) -> None:
        self._req("POST", f"/users/{uid}/declines")

    def latest_story(self, uid: int) -> dict[str, Any] | None:
        return self._req("GET", f"/users/{uid}/stories/latest")  # type: ignore[no-any-return]

    def delete_story(self, uid: int, story_id: int) -> None:
        self._req("DELETE", f"/users/{uid}/stories/{story_id}")

    def opener_allowed(self, uid: int) -> bool:
        return bool(self._req("GET", f"/users/{uid}/opener-allowed")["allowed"])

    def mark_seen(self, uid: int, how: str = "voice") -> None:
        """'Last talked to Arjun' for the family: the time only, never the words."""
        self._req("POST", f"/users/{uid}/activity", json={"how": how})

    def lonely(self, uid: int) -> bool:
        """Tells the family (with consent, once a day) that she said she feels lonely. Never her words."""
        return bool(self._req("POST", f"/users/{uid}/lonely")["family_told"])

    def health_complaint(self, uid: int, category: str) -> bool:
        """Tells the family (with consent, once a day per kind) that she mentioned a health complaint. No advice,
        never her words. Returns whether a note exists for the family."""
        return bool(
            self._req("POST", f"/users/{uid}/health-complaint", params={"category": category})["family_told"]
        )

    def app_links(self, uid: int) -> list[dict[str, Any]]:
        """The apps and links the family allowed (YouTube favourites, news feeds, WhatsApp, web links)."""
        return self._req("GET", f"/users/{uid}/app-links")  # type: ignore[no-any-return]

    def app_match(self, uid: int, q: str) -> dict[str, Any] | None:
        """The family's app whose label / spoken name appears whole in `q` (core-api's own match), or null."""
        return self._req("GET", f"/users/{uid}/apps/match", params={"q": q})  # type: ignore[no-any-return]

    def youtube_search(self, uid: int, q: str, kind: str | None = None) -> list[dict[str, str]]:
        """[{video_id, title, channel}] from core-api (the YouTube key never leaves it). 503 = no key, 429 = quota.
        kind="news_video" asks core-api for live Marathi news."""
        params: dict[str, Any] = {"q": q, "user_id": uid}
        if kind:
            params["kind"] = kind
        return self._req("GET", "/media/youtube/search", params=params)  # type: ignore[no-any-return]

    def news(self, uid: int) -> list[dict[str, str]]:
        """Top headlines [{source_label, title}] from the family's feeds, verbatim; [] when none could be read."""
        return self._req("GET", "/media/news", params={"user_id": uid})  # type: ignore[no-any-return]

    def undo(self, uid: int, action_id: int) -> dict[str, Any]:
        """Put back an action Arjun just did ("नको / चुकलं"). core-api refuses after its undo window."""
        return self._req("POST", f"/users/{uid}/actions/{action_id}/undo")  # type: ignore[no-any-return]

    def wellbeing(self, uid: int, entry: dict[str, Any]) -> dict[str, Any]:
        """One conversation summary for the family: seriousness, mood, a short paraphrase. Never a transcript."""
        return self._req("POST", f"/users/{uid}/wellbeing", json=entry)  # type: ignore[no-any-return]
