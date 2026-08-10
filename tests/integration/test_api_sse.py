import time

from fastapi.testclient import TestClient

from code_agent.api.app import create_app


def wait_for_status(client: TestClient, task_id: str, status: str) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if client.get(f"/api/tasks/{task_id}").json()["status"] == status:
            return
        time.sleep(0.01)
    raise AssertionError(f"task did not reach {status}")


def test_create_task_returns_task_id(tmp_path) -> None:
    client = TestClient(create_app(state_path=tmp_path / "state.db"))
    response = client.post(
        "/api/tasks",
        json={"workspace": str(tmp_path), "goal": "inspect", "mode": "plan", "provider": "mock"},
    )
    assert response.status_code == 201
    assert response.json()["id"]
    assert response.json()["status"] in {"pending", "running", "needs_review"}


def test_events_endpoint_replays_ordered_events(tmp_path) -> None:
    client = TestClient(create_app(state_path=tmp_path / "state.db"))
    task_id = client.post(
        "/api/tasks", json={"workspace": str(tmp_path), "goal": "inspect"}
    ).json()["id"]
    response = client.get(f"/api/tasks/{task_id}/events?after=0")
    assert response.status_code == 200
    assert isinstance(response.json()["events"], list)


def test_create_task_returns_before_worker_finishes(tmp_path) -> None:
    app = create_app(state_path=tmp_path / "state.db")
    with TestClient(app) as client:
        response = client.post(
            "/api/tasks",
            json={
                "workspace": str(tmp_path),
                "goal": "complete",
                "provider": "mock",
                "mock_decisions": [
                    {"action": "complete", "completion_message": "done"}
                ],
            },
        )

        assert response.status_code == 201
        assert response.json()["id"]
        wait_for_status(client, response.json()["id"], "succeeded")


def test_approval_endpoint_decides_pending_approval(tmp_path) -> None:
    app = create_app(state_path=tmp_path / "state.db")
    with TestClient(app) as client:
        response = client.post(
            "/api/tasks",
            json={
                "workspace": str(tmp_path),
                "goal": "shell",
                "mock_decisions": [
                    {
                        "action": "tool_call",
                        "tool_action": {
                            "tool": "shell",
                            "arguments": {"command": 'python -c "pass"'},
                        },
                    },
                    {"action": "complete", "completion_message": "done"},
                ],
            },
        )
        task_id = response.json()["id"]
        wait_for_status(client, task_id, "waiting_approval")
        approval_id = client.get(f"/api/tasks/{task_id}").json()["pending_approvals"][0]["id"]

        decision = client.post(
            f"/api/approvals/{approval_id}/decision",
            json={"approved": True, "scope": "once"},
        )

        assert decision.status_code == 200
        wait_for_status(client, task_id, "succeeded")


def test_events_stream_replays_after_cursor_and_closes_at_terminal(tmp_path) -> None:
    app = create_app(state_path=tmp_path / "state.db")
    with TestClient(app) as client:
        task_id = client.post(
            "/api/tasks",
            json={
                "workspace": str(tmp_path),
                "goal": "complete",
                "mock_decisions": [
                    {"action": "complete", "completion_message": "done"}
                ],
            },
        ).json()["id"]
        wait_for_status(client, task_id, "succeeded")

        with client.stream("GET", f"/api/tasks/{task_id}/events/stream?after=1") as response:
            body = response.read().decode()

        assert response.status_code == 200
        assert "id: 2" in body
        assert "event: task_completed" in body


def test_cancel_waiting_approval_task_returns_cancelled(tmp_path) -> None:
    app = create_app(state_path=tmp_path / "state.db")
    with TestClient(app) as client:
        task_id = client.post(
            "/api/tasks",
            json={
                "workspace": str(tmp_path),
                "goal": "shell",
                "mock_decisions": [
                    {
                        "action": "tool_call",
                        "tool_action": {
                            "tool": "shell",
                            "arguments": {"command": 'python -c "pass"'},
                        },
                    }
                ],
            },
        ).json()["id"]
        wait_for_status(client, task_id, "waiting_approval")

        response = client.post(f"/api/tasks/{task_id}/cancel")

        assert response.status_code == 200
        wait_for_status(client, task_id, "cancelled")


def test_terminal_task_cannot_be_cancelled_twice(tmp_path) -> None:
    app = create_app(state_path=tmp_path / "state.db")
    with TestClient(app) as client:
        task_id = client.post(
            "/api/tasks",
            json={
                "workspace": str(tmp_path),
                "goal": "complete",
                "mock_decisions": [
                    {"action": "complete", "completion_message": "done"}
                ],
            },
        ).json()["id"]
        wait_for_status(client, task_id, "succeeded")

        response = client.post(f"/api/tasks/{task_id}/cancel")

        assert response.status_code == 409
