from __future__ import annotations

from typing import Any, Literal, cast

import httpx


class TaskApiError(Exception):
    """A safe, user-facing error returned by the task API client."""


class TaskApiClient:
    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client()

    def create_task(self, payload: dict[str, object]) -> dict[str, object]:
        return self._request("POST", "/api/tasks", json=payload)

    def get_task(self, task_id: str) -> dict[str, object]:
        return self._request("GET", f"/api/tasks/{task_id}")

    def get_events(self, task_id: str, after: int) -> dict[str, object]:
        return self._request("GET", f"/api/tasks/{task_id}/events", params={"after": after})

    def cancel_task(self, task_id: str) -> dict[str, object]:
        return self._request("POST", f"/api/tasks/{task_id}/cancel")

    def resume_task(self, task_id: str) -> dict[str, object]:
        return self._request("POST", f"/api/tasks/{task_id}/resume")

    def get_report(self, task_id: str) -> dict[str, object]:
        return self._request("GET", f"/api/tasks/{task_id}/report")

    def get_diff(self, task_id: str) -> dict[str, object]:
        return self._request("GET", f"/api/tasks/{task_id}/diff")

    def decide_approval(
        self, approval_id: str, *, approved: bool, scope: Literal["once", "task"]
    ) -> dict[str, object]:
        return self._request(
            "POST",
            f"/api/approvals/{approval_id}/decision",
            json={"approved": approved, "scope": scope, "actor": "tui-user"},
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, object]:
        try:
            response = self._client.request(method, f"{self._base_url}{path}", **kwargs)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TaskApiError("Task service is unavailable.") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise TaskApiError("Task service returned an invalid response.") from exc
        if not isinstance(payload, dict):
            raise TaskApiError("Task service returned an invalid response.")
        return cast(dict[str, object], payload)
