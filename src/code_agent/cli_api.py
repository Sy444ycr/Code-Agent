from __future__ import annotations

from typing import Any, cast

import httpx


class TaskApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = httpx.request(method, f"{self.base_url}{path}", timeout=30, **kwargs)
            response.raise_for_status()
            return cast(dict[str, Any], response.json())
        except httpx.HTTPError as exc:
            raise ValueError("服务请求失败。") from exc

    def get_status(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/tasks/{task_id}")

    def decide_approval(
        self, approval_id: str, approved: bool, scope: str = "once"
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/approvals/{approval_id}/decision",
            json={"approved": approved, "scope": scope},
        )

    def resume_task(self, task_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/tasks/{task_id}/resume")

    def get_diff(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/tasks/{task_id}/diff")

    def get_report(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/tasks/{task_id}/report")
