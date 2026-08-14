import json
import time
from threading import Event

import pytest
from fastapi.testclient import TestClient

import code_agent.api.app as api_app
from code_agent.api.app import create_app
from code_agent.core.llm import MockLLMProvider
from code_agent.core.models import (
    AgentDecision,
    Approval,
    LoopSpec,
    PermissionMode,
    Task,
    TaskRecovery,
    TaskStatus,
    ToolAction,
)
from code_agent.storage import SQLiteStore


def wait_for_status(client: TestClient, task_id: str, status: str) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if client.get(f"/api/tasks/{task_id}").json()["status"] == status:
            return
        time.sleep(0.01)
    raise AssertionError(f"task did not reach {status}")


def wait_for_task_completed(client: TestClient, task_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        events = client.get(f"/api/tasks/{task_id}/events?after=0").json()["events"]
        for event in reversed(events):
            if event["type"] == "task_completed":
                return event
        time.sleep(0.01)
    raise AssertionError("task_completed event was not persisted")


def read_sse_events(client: TestClient, path: str) -> list[dict[str, object]]:
    with client.stream("GET", path) as response:
        body = response.read().decode()

    assert response.status_code == 200
    return [_parse_sse_block(block) for block in body.split("\n\n") if block.strip()]


def _parse_sse_block(block: str) -> dict[str, object]:
    parsed: dict[str, object] = {}
    for line in block.splitlines():
        if line.startswith("id: "):
            parsed["id"] = int(line[4:])
        elif line.startswith("event: "):
            parsed["event"] = line[7:]
        elif line.startswith("data: "):
            parsed["data"] = json.loads(line[6:])
    return parsed


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
        wait_for_task_completed(client, task_id)

        with client.stream("GET", f"/api/tasks/{task_id}/events/stream?after=1") as response:
            body = response.read().decode()

        assert response.status_code == 200
        assert "id: 2" in body
        assert "event: task_completed" in body


def test_events_stream_closes_when_cursor_is_task_completed_sequence(
    tmp_path, monkeypatch
) -> None:
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
        completion = wait_for_task_completed(client, task_id)

        def fail_wait(*args, **kwargs) -> None:
            del args, kwargs
            raise AssertionError("completed cursor must not wait for another event")

        monkeypatch.setattr(client.app.state.manager, "wait_for_event", fail_wait)
        events = read_sse_events(
            client,
            f"/api/tasks/{task_id}/events/stream?after={completion['sequence']}",
        )

        assert events == []


def test_events_stream_replays_terminal_completion_before_closing(tmp_path) -> None:
    app = create_app(state_path=tmp_path / "state.db")
    with TestClient(app) as client:
        task = client.app.state.store.create_task(
            Task(
                workspace=str(tmp_path),
                goal="complete",
                provider="mock",
                status=TaskStatus.SUCCEEDED,
            ),
            LoopSpec(goal="complete"),
        )
        feedback_event = client.app.state.store.append_event(
            task.id, "feedback", {"changed_files": ["marker.txt"]}
        )
        completion_event = client.app.state.store.append_event(
            task.id,
            "task_completed",
            {
                "status": "succeeded",
                "report": "done",
                "changed_files": ["marker.txt"],
                "feedback": [],
                "verification": [],
            },
        )

        events_after_calls = 0
        original_events_after = client.app.state.store.events_after

        def staged_events_after(task_id: str, after: int):
            nonlocal events_after_calls
            events_after_calls += 1
            if events_after_calls == 1:
                assert after == 0
                return [feedback_event]
            if events_after_calls == 2:
                assert after == feedback_event.sequence
                return [completion_event]
            return original_events_after(task_id, after)

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(client.app.state.store, "events_after", staged_events_after)
        try:
            events = read_sse_events(client, f"/api/tasks/{task.id}/events/stream?after=0")
        finally:
            monkeypatch.undo()

        assert [event["event"] for event in events] == ["feedback", "task_completed"]
        assert events[-1]["data"]["payload"]["status"] == "succeeded"


def test_events_stream_waits_for_active_runtime_needs_review_completion(
    tmp_path, monkeypatch
) -> None:
    app = create_app(state_path=tmp_path / "state.db")
    completion_append_entered = Event()
    allow_completion_append = Event()
    original_append_event = app.state.store.append_event

    def block_completion_append(task_id: str, event_type: str, payload: dict[str, object]):
        if event_type == "task_completed":
            completion_append_entered.set()
            assert allow_completion_append.wait(timeout=2)
        return original_append_event(task_id, event_type, payload)

    monkeypatch.setattr(app.state.store, "append_event", block_completion_append)
    with TestClient(app) as client:
        task = Task(
            workspace=str(tmp_path),
            goal="deny shell",
            mode=PermissionMode.PLAN,
            provider="mock",
        )
        client.app.state.manager.submit(
            task,
            LoopSpec(goal=task.goal),
            MockLLMProvider([
                AgentDecision(
                    action="tool_call",
                    tool_action=ToolAction(
                        tool="shell", arguments={"command": 'python -c "pass"'}
                    ),
                )
            ]),
        )
        assert completion_append_entered.wait(timeout=2)
        assert client.app.state.store.get_task(task.id).status == TaskStatus.NEEDS_REVIEW
        assert task.id in client.app.state.manager._runtimes

        original_wait_for_event = client.app.state.manager.wait_for_event
        waited_for_active_runtime = False

        def release_completion_on_wait(task_id: str, after: int, timeout: float) -> None:
            nonlocal waited_for_active_runtime
            waited_for_active_runtime = True
            allow_completion_append.set()
            original_wait_for_event(task_id, after, timeout)

        monkeypatch.setattr(
            client.app.state.manager, "wait_for_event", release_completion_on_wait
        )
        try:
            events = read_sse_events(
                client, f"/api/tasks/{task.id}/events/stream?after=0"
            )
        finally:
            allow_completion_append.set()

        assert waited_for_active_runtime
        assert events[-1]["event"] == "task_completed"
        assert events[-1]["data"]["payload"]["status"] == "needs_review"


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
        wait_for_task_completed(client, task.id)
        events = client.get(f"/api/tasks/{task.id}/events?after=0").json()["events"]
        event_types = [event["type"] for event in events]
        assert event_types[0] == "recovery_required"
        assert "recovery_started" in event_types
        assert event_types[-1] == "task_completed"
        assert event_types.index("recovery_started") < event_types.index("task_completed")


def test_restart_recovery_events_endpoint_requires_manual_resume_and_preserves_order(
    tmp_path,
) -> None:
    state_path = tmp_path / "state.db"
    old_app = create_app(state_path=state_path)
    seeded_task = old_app.state.store.create_task(
        Task(
            workspace=str(tmp_path),
            goal="stale-goal",
            provider="mock",
            status=TaskStatus.WAITING_APPROVAL,
        ),
        LoopSpec(goal="persisted-goal"),
        recovery=TaskRecovery(
            mock_decisions=[
                AgentDecision(action="complete", completion_message="done after resume")
            ]
        ),
    )
    seeded_approval = old_app.state.store.save_approval(
        Approval(
            task_id=seeded_task.id,
            tool_call_id="tool-1",
            reason="shell requires approval",
        )
    )
    old_app.state.manager.shutdown()

    with TestClient(create_app(state_path=state_path)) as client:
        detail = client.get(f"/api/tasks/{seeded_task.id}")

        assert detail.status_code == 200
        assert detail.json()["status"] == "needs_review"
        assert detail.json()["goal"] == "stale-goal"
        assert detail.json()["loop_spec"]["goal"] == "persisted-goal"
        assert detail.json()["recovery_required"] is True
        assert detail.json()["recovery_reason"] == "服务重启后需人工复核"
        assert detail.json()["resumable"] is True
        assert detail.json()["pending_approvals"] == [
            seeded_approval.model_dump(mode="json")
        ]

        events_before_resume = client.get(f"/api/tasks/{seeded_task.id}/events?after=0")
        assert [event["type"] for event in events_before_resume.json()["events"]] == [
            "recovery_required"
        ]

        resume = client.post(f"/api/tasks/{seeded_task.id}/resume")

        assert resume.status_code == 200
        wait_for_task_completed(client, seeded_task.id)

        final_detail = client.get(f"/api/tasks/{seeded_task.id}")
        assert final_detail.status_code == 200
        assert final_detail.json()["status"] == "succeeded"
        assert final_detail.json()["goal"] == "persisted-goal"
        assert final_detail.json()["recovery_required"] is False
        assert final_detail.json()["recovery_reason"] is None
        assert final_detail.json()["resumable"] is False

        events = client.get(f"/api/tasks/{seeded_task.id}/events?after=0").json()["events"]
        sequences = [event["sequence"] for event in events]
        event_types = [event["type"] for event in events]

        assert sequences == list(range(1, len(events) + 1))
        assert event_types[0] == "recovery_required"
        assert "recovery_started" in event_types
        assert event_types[-1] == "task_completed"
        assert event_types.index("recovery_required") < event_types.index("recovery_started")
        assert event_types.index("recovery_started") < event_types.index("task_completed")
        assert "approval_decided" not in event_types
        assert events[-1]["payload"]["status"] == "succeeded"
        assert events[-1]["payload"]["report"] == "done after resume"


def test_restart_recovery_events_stream_replays_first_step_only_after_resume(tmp_path) -> None:
    state_path = tmp_path / "state.db"
    old_app = create_app(state_path=state_path)
    seeded_task = old_app.state.store.create_task(
        Task(
            workspace=str(tmp_path),
            goal="stale-goal",
            provider="mock",
            status=TaskStatus.WAITING_APPROVAL,
        ),
        LoopSpec(goal="persisted-goal"),
        recovery=TaskRecovery(
            mock_decisions=[
                AgentDecision(
                    action="tool_call",
                    tool_action=ToolAction(
                        tool="write_file",
                        arguments={"path": "restart-marker.txt", "content": "from-recovery"},
                    ),
                ),
                AgentDecision(action="complete", completion_message="done after resume"),
            ]
        ),
    )
    seeded_approval = old_app.state.store.save_approval(
        Approval(
            task_id=seeded_task.id,
            tool_call_id="tool-1",
            reason="shell requires approval",
        )
    )
    old_app.state.manager.shutdown()

    with TestClient(create_app(state_path=state_path)) as client:
        detail = client.get(f"/api/tasks/{seeded_task.id}")

        assert detail.status_code == 200
        assert detail.json()["status"] == "needs_review"
        assert detail.json()["goal"] == "stale-goal"
        assert detail.json()["loop_spec"]["goal"] == "persisted-goal"
        assert detail.json()["recovery_required"] is True
        assert detail.json()["resumable"] is True
        assert detail.json()["pending_approvals"] == [
            seeded_approval.model_dump(mode="json")
        ]

        stale_decision = client.post(
            f"/api/approvals/{seeded_approval.id}/decision",
            json={"approved": True, "scope": "once"},
        )
        assert stale_decision.status_code == 409

        events_before_resume = read_sse_events(
            client, f"/api/tasks/{seeded_task.id}/events/stream?after=0"
        )
        assert [event["event"] for event in events_before_resume] == [
            "recovery_required"
        ]
        assert all(event["event"] != "task_completed" for event in events_before_resume)

        resume = client.post(f"/api/tasks/{seeded_task.id}/resume")

        assert resume.status_code == 200
        wait_for_task_completed(client, seeded_task.id)
        resumed_events = read_sse_events(
            client,
            f"/api/tasks/{seeded_task.id}/events/stream?after={events_before_resume[-1]['id']}",
        )

        final_detail = client.get(f"/api/tasks/{seeded_task.id}")
        assert final_detail.status_code == 200
        assert final_detail.json()["status"] == "succeeded"
        assert final_detail.json()["goal"] == "persisted-goal"
        assert final_detail.json()["recovery_required"] is False
        assert final_detail.json()["recovery_reason"] is None
        assert final_detail.json()["resumable"] is False

        all_events = events_before_resume + resumed_events
        all_sequences = [event["id"] for event in all_events]
        resumed_event_types = [event["event"] for event in resumed_events]
        feedback_event = next(event for event in resumed_events if event["event"] == "feedback")
        completion_event = next(
            event for event in resumed_events if event["event"] == "task_completed"
        )

        assert all_sequences == list(range(1, len(all_events) + 1))
        assert resumed_event_types[0] == "recovery_started"
        assert "feedback" in resumed_event_types
        assert resumed_event_types[-1] == "task_completed"
        assert resumed_event_types.index("recovery_started") < resumed_event_types.index("feedback")
        assert resumed_event_types.index("feedback") < resumed_event_types.index("task_completed")
        assert feedback_event["data"]["payload"]["changed_files"] == ["restart-marker.txt"]
        assert completion_event["data"]["payload"]["status"] == "succeeded"
        assert completion_event["data"]["payload"]["report"] == "done after resume"
        assert (tmp_path / "restart-marker.txt").read_text(encoding="utf-8") == "from-recovery"


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
