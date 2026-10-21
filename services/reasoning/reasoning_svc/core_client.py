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

    def day(self, uid: int) -> dict[str, Any]:
        return self._req("GET", f"/users/{uid}/day")  # type: ignore[no-any-return]

    def due_medicines(self, uid: int) -> dict[str, Any]:
        return self._req("GET", f"/users/{uid}/medicines/due")  # type: ignore[no-any-return]

    def pending(self, uid: int) -> dict[str, Any] | None:
        return self._req("GET", f"/users/{uid}/actions/pending")  # type: ignore[no-any-return]

    def propose(self, uid: int, action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = {"action_type": action_type, "payload": payload}
        return self._req("POST", f"/users/{uid}/actions/propose", json=body)  # type: ignore[no-any-return]

    def confirm(self, uid: int, action_id: int) -> dict[str, Any]:
        return self._req("POST", f"/users/{uid}/actions/{action_id}/confirm")  # type: ignore[no-any-return]

    def reject(self, uid: int, action_id: int) -> dict[str, Any]:
        return self._req("POST", f"/users/{uid}/actions/{action_id}/reject")  # type: ignore[no-any-return]

    def distress(self, uid: int) -> dict[str, Any]:
        return self._req("POST", f"/users/{uid}/distress")  # type: ignore[no-any-return]

    def decline(self, uid: int) -> None:
        self._req("POST", f"/users/{uid}/declines")

    def latest_story(self, uid: int) -> dict[str, Any] | None:
        return self._req("GET", f"/users/{uid}/stories/latest")  # type: ignore[no-any-return]

    def delete_story(self, uid: int, story_id: int) -> None:
        self._req("DELETE", f"/users/{uid}/stories/{story_id}")

    def opener_allowed(self, uid: int) -> bool:
        return bool(self._req("GET", f"/users/{uid}/opener-allowed")["allowed"])
