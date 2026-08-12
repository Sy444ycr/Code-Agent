from __future__ import annotations

import json

import httpx
import pytest

from code_agent.tui.api import TaskApiClient, TaskApiError


def test_task_api_client_uses_task_api_routes_and_payloads() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/tasks" and request.method == "POST":
            return httpx.Response(201, json={"id": "task-1", "status": "running"})
        if request.url.path == "/api/tasks/task-1" and request.method == "GET":
            return httpx.Response(200, json={"id": "task-1", "status": "running"})
        if request.url.path == "/api/tasks/task-1/events":
            return httpx.Response(200, json={"events": [{"sequence": 2, "type": "started"}]})
        if request.url.path.endswith("/cancel"):
            return httpx.Response(200, json={"id": "task-1", "status": "cancelled"})
        if request.url.path.endswith("/resume"):
            return httpx.Response(200, json={"id": "task-1", "status": "running"})
        if request.url.path == "/api/approvals/approval-1/decision":
            return httpx.Response(
                200,
                json={"approval": {"id": "approval-1", "status": "approved"}},
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = TaskApiClient(
        "https://task.example/",
        httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert client.create_task("C:/repo", "Ship the TUI") == {"id": "task-1", "status": "running"}
    assert client.get_task("task-1") == {"id": "task-1", "status": "running"}
    assert client.get_events("task-1", after=1) == {
        "events": [{"sequence": 2, "type": "started"}]
    }
    assert client.cancel_task("task-1") == {"id": "task-1", "status": "cancelled"}
    assert client.resume_task("task-1") == {"id": "task-1", "status": "running"}
    assert client.decide_approval("approval-1", approved=True, scope="task") == {
        "approval": {"id": "approval-1", "status": "approved"}
    }

    assert [(request.method, request.url.path) for request in requests] == [
        ("POST", "/api/tasks"),
        ("GET", "/api/tasks/task-1"),
        ("GET", "/api/tasks/task-1/events"),
        ("POST", "/api/tasks/task-1/cancel"),
        ("POST", "/api/tasks/task-1/resume"),
        ("POST", "/api/approvals/approval-1/decision"),
    ]
    assert json.loads(requests[0].content) == {
        "workspace": "C:/repo",
        "goal": "Ship the TUI",
        "mode": "supervised",
        "provider": "mock",
        "acceptance_checks": [],
    }
    assert requests[2].url.params == httpx.QueryParams({"after": "1"})
    assert json.loads(requests[5].content) == {
        "approved": True,
        "scope": "task",
        "actor": "tui-user",
    }


@pytest.mark.parametrize(
    ("response", "expected_error"),
    [
        (httpx.Response(503, text="database password: secret"), "Task service is unavailable."),
        (httpx.Response(200, content=b"not json"), "Task service returned an invalid response."),
    ],
)
def test_task_api_client_converts_transport_failures_to_safe_errors(
    response: httpx.Response, expected_error: str
) -> None:
    client = TaskApiClient(
        "https://task.example",
        httpx.Client(transport=httpx.MockTransport(lambda request: response)),
    )

    with pytest.raises(TaskApiError, match=f"^{expected_error}$"):
        client.get_task("task-1")
