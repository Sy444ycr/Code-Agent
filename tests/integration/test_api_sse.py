import time

import pytest
from fastapi.testclient import TestClient

import code_agent.api.app as api_app
from code_agent.api.app import create_app
from code_agent.core.models import AgentDecision, LoopSpec, Task, TaskRecovery, TaskStatus
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
    assert recovery.mock_decisions == [
        AgentDecision.model_validate(decision) for decision in decisions
    ]


def test_resume_rebuilds_mock_provider_after_startup_isolation(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    task = store.create_task(
        Task(
            workspace=str(tmp_path),
            goal="stale-goal",
            provider="mock",
            status=TaskStatus.RUNNING,
        ),
        LoopSpec(goal="persisted-goal"),
    )
    store.save_recovery(
        task.id,
        TaskRecovery(
            mock_decisions=[AgentDecision(action="complete", completion_message="done again")]
        ),
    )

    with TestClient(create_app(store=store)) as client:
        detail = client.get(f"/api/tasks/{task.id}")
        response = client.post(f"/api/tasks/{task.id}/resume")

        assert detail.status_code == 200
        assert detail.json()["status"] == "needs_review"
        assert detail.json()["goal"] == "stale-goal"
        assert detail.json()["recovery_required"] is True
        assert detail.json()["resumable"] is True

        assert response.status_code == 200
        wait_for_status(client, task.id, "succeeded")
        events = client.get(f"/api/tasks/{task.id}/events?after=0").json()["events"]
        event_types = [event["type"] for event in events]
        assert event_types[0] == "recovery_required"
        assert "recovery_started" in event_types
        assert event_types[-1] == "task_completed"
        assert event_types.index("recovery_started") < event_types.index("task_completed")


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


def test_resume_rejects_provider_reconstruction_failure_without_starting_recovery(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    task = store.create_task(
        Task(
            workspace=str(tmp_path),
            goal="recover",
            provider="mock",
            status=TaskStatus.NEEDS_REVIEW,
        ),
        LoopSpec(goal="recover"),
    )
    store.save_recovery(
        task.id,
        TaskRecovery(
            required=True,
            reason="服务重启后需人工复核",
            mock_decisions=[AgentDecision(action="complete", completion_message="done")],
        ),
    )

    def fail_build_provider(
        name,
        workspace,
        *,
        mock_decisions=None,
        allow_development_fallback=False,
    ):
        del name, workspace, mock_decisions, allow_development_fallback
        raise api_app.ProviderFactoryError("Provider 配置不可用。")

    monkeypatch.setattr(api_app, "build_provider", fail_build_provider)

    with TestClient(create_app(store=store)) as client:
        def fail_recover(task_id, provider):
            raise AssertionError(f"recover should not be called for {task_id} {provider}")

        monkeypatch.setattr(client.app.state.manager, "recover", fail_recover)
        response = client.post(f"/api/tasks/{task.id}/resume")
        detail = client.get(f"/api/tasks/{task.id}")
        events = client.get(f"/api/tasks/{task.id}/events?after=0")

    assert response.status_code == 409
    assert response.json()["detail"] == "Provider 配置不可用。"
    assert detail.json()["status"] == "needs_review"
    assert all(event["type"] != "recovery_started" for event in events.json()["events"])
