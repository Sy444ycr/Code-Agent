import time

from fastapi.testclient import TestClient

from code_agent.api.app import create_app
from code_agent.core.models import AgentDecision
from code_agent.core.models import LoopSpec, Task, TaskRecovery, TaskStatus
from code_agent.storage import SQLiteStore


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
    assert response.json()["provider"] == "mock"


def test_create_task_rejects_unconfigured_provider_before_submit(tmp_path) -> None:
    app = create_app(state_path=tmp_path / "state.db")
    with TestClient(app) as client:
        response = client.post(
            "/api/tasks",
            json={
                "workspace": str(tmp_path),
                "goal": "inspect",
                "provider": "openai",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Provider 配置不可用。"


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


def test_get_task_reports_recovery_summary_and_resumable_only_for_restart_recovery(
    tmp_path,
) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    resumable_task = store.create_task(
        Task(workspace=str(tmp_path), goal="recover", status=TaskStatus.NEEDS_REVIEW),
        LoopSpec(goal="recover"),
    )
    store.save_recovery(
        resumable_task.id,
        TaskRecovery(required=True, reason="服务重启后需人工复核"),
    )
    manual_review_task = store.create_task(
        Task(workspace=str(tmp_path), goal="manual", status=TaskStatus.NEEDS_REVIEW),
        LoopSpec(goal="manual"),
    )

    with TestClient(create_app(store=store)) as client:
        resumable_response = client.get(f"/api/tasks/{resumable_task.id}")
        manual_response = client.get(f"/api/tasks/{manual_review_task.id}")

    assert resumable_response.status_code == 200
    assert resumable_response.json()["recovery_required"] is True
    assert resumable_response.json()["recovery_reason"] == "服务重启后需人工复核"
    assert resumable_response.json()["resumable"] is True

    assert manual_response.status_code == 200
    assert manual_response.json()["recovery_required"] is False
    assert manual_response.json()["recovery_reason"] is None
    assert manual_response.json()["resumable"] is False


def test_create_task_persists_mock_decisions_for_recovery(tmp_path) -> None:
    app = create_app(state_path=tmp_path / "state.db")
    decisions = [{"action": "complete", "completion_message": "done"}]

    with TestClient(app) as client:
        task_id = client.post(
            "/api/tasks",
            json={
                "workspace": str(tmp_path),
                "goal": "complete",
                "provider": "mock",
                "mock_decisions": decisions,
            },
        ).json()["id"]

    recovery = app.state.store.get_recovery(task_id)

    assert recovery is not None
    assert recovery.required is False
    assert recovery.reason is None
    assert recovery.mock_decisions == [AgentDecision.model_validate(decision) for decision in decisions]


def test_resume_rebuilds_mock_provider_for_restart_recovery(tmp_path) -> None:
    state_path = tmp_path / "state.db"
    initial_app = create_app(state_path=state_path)
    decisions = [{"action": "complete", "completion_message": "done again"}]

    with TestClient(initial_app) as client:
        task_id = client.post(
            "/api/tasks",
            json={
                "workspace": str(tmp_path),
                "goal": "complete",
                "provider": "mock",
                "mock_decisions": decisions,
            },
        ).json()["id"]
        wait_for_status(client, task_id, "succeeded")

        task = initial_app.state.store.get_task(task_id)
        assert task is not None
        initial_app.state.store.update_task(
            task.model_copy(update={"status": TaskStatus.NEEDS_REVIEW})
        )
        recovery = initial_app.state.store.get_recovery(task_id)
        assert recovery is not None
        initial_app.state.store.save_recovery(
            task_id,
            recovery.model_copy(update={"required": True, "reason": "服务重启后需人工复核"}),
        )

    restarted_app = create_app(state_path=state_path)
    with TestClient(restarted_app) as client:
        detail = client.get(f"/api/tasks/{task_id}")
        response = client.post(f"/api/tasks/{task_id}/resume")

        assert detail.status_code == 200
        assert detail.json()["status"] == "needs_review"
        assert detail.json()["recovery_required"] is True
        assert detail.json()["resumable"] is True

        assert response.status_code == 200
        wait_for_status(client, task_id, "succeeded")
        assert any(
            event["type"] == "recovery_started"
            for event in client.get(f"/api/tasks/{task_id}/events?after=0").json()["events"]
        )


def test_resume_rejects_missing_workspace_without_starting_recovery(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    missing_workspace = tmp_path / "missing-workspace"
    task = store.create_task(
        Task(
            workspace=str(missing_workspace),
            goal="recover",
            status=TaskStatus.NEEDS_REVIEW,
        ),
        LoopSpec(goal="recover"),
    )
    store.save_recovery(task.id, TaskRecovery(required=True, reason="服务重启后需人工复核"))

    with TestClient(create_app(store=store)) as client:
        response = client.post(f"/api/tasks/{task.id}/resume")
        detail = client.get(f"/api/tasks/{task.id}")
        events = client.get(f"/api/tasks/{task.id}/events?after=0")

    assert response.status_code == 409
    assert response.json()["detail"] == "workspace does not exist"
    assert detail.json()["status"] == "needs_review"
    assert all(event["type"] != "recovery_started" for event in events.json()["events"])
