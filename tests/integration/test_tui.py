import asyncio
import threading
from collections.abc import Callable
from typing import Literal

import httpx
import pytest
from textual.widgets import Input, Static

from code_agent.tui.api import TaskApiClient, TaskApiError
from code_agent.tui.app import CodeAgentTui
from code_agent.tui.screens import ApprovalScreen, ResultScreen, RunScreen


class FakeTaskApiClient:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def create_task(self, payload: dict[str, object]) -> dict[str, object]:
        self.payloads.append(payload)
        return {"id": "task-1", "status": "running"}


class FailingTaskApiClient:
    def create_task(self, payload: dict[str, object]) -> dict[str, object]:
        del payload
        raise TaskApiError("Task service is unavailable.")


class RuntimeTaskApiClient(FakeTaskApiClient):
    def __init__(
        self,
        status: str = "running",
        *,
        events_for_after: dict[int, list[dict[str, object]]] | None = None,
        result_report: str | None = None,
        recovery_required: bool = False,
        recovery_reason: str | None = None,
        resumable: bool = False,
    ) -> None:
        super().__init__()
        self.status = status
        self.events_for_after = events_for_after or {}
        self.result_report = result_report
        self.recovery_required = recovery_required
        self.recovery_reason = recovery_reason
        self.resumable = resumable
        self.task_reads = 0
        self.event_afters: list[int] = []
        self.decisions: list[tuple[str, bool, str]] = []
        self.cancel_calls = 0
        self.resume_calls = 0
        self.fail_next_task_read = False
        self.fail_event_reads = False
        self.fail_cancel = False
        self.fail_resume = False

    def get_task(self, task_id: str) -> dict[str, object]:
        assert task_id == "task-1"
        self.task_reads += 1
        if self.fail_next_task_read:
            self.fail_next_task_read = False
            raise TaskApiError("Task service is unavailable.")
        detail: dict[str, object] = {
            "id": task_id,
            "status": self.status,
            "goal": "Ship the TUI",
            "pending_approvals": [],
            "recovery_required": self.recovery_required,
            "recovery_reason": self.recovery_reason,
            "resumable": self.resumable,
        }
        if self.status == "waiting_approval":
            detail["pending_approvals"] = [
                {"id": "approval-1", "reason": "需要执行测试", "scope": "once"}
            ]
        if self.result_report is not None:
            detail["result_report"] = self.result_report
        return detail

    def get_events(self, task_id: str, after: int) -> dict[str, object]:
        assert task_id == "task-1"
        self.event_afters.append(after)
        if self.fail_event_reads:
            raise TaskApiError("Task service is unavailable.")
        return {"events": self.events_for_after.get(after, [])}

    def decide_approval(
        self, approval_id: str, *, approved: bool, scope: Literal["once", "task"]
    ) -> dict[str, object]:
        self.decisions.append((approval_id, approved, scope))
        self.status = "running"
        return {"approval": {"id": approval_id, "status": "approved"}}

    def cancel_task(self, task_id: str) -> dict[str, object]:
        assert task_id == "task-1"
        self.cancel_calls += 1
        if self.fail_cancel:
            raise TaskApiError("Task service is unavailable.")
        self.status = "cancelled"
        return {"id": task_id, "status": self.status}

    def resume_task(self, task_id: str) -> dict[str, object]:
        assert task_id == "task-1"
        self.resume_calls += 1
        if self.fail_resume:
            raise TaskApiError("Task service is unavailable.")
        self.status = "running"
        return {"id": task_id, "status": self.status}


class BlockingCancelTaskApiClient(RuntimeTaskApiClient):
    def __init__(self) -> None:
        super().__init__()
        self.first_read_started = threading.Event()
        self.release_first_read = threading.Event()
        self._active_reads = 0
        self.max_active_reads = 0
        self._read_lock = threading.Lock()

    def get_task(self, task_id: str) -> dict[str, object]:
        assert task_id == "task-1"
        with self._read_lock:
            self._active_reads += 1
            self.max_active_reads = max(self.max_active_reads, self._active_reads)
        try:
            self.task_reads += 1
            if self.task_reads == 1:
                snapshot = {
                    "id": task_id,
                    "status": "running",
                    "goal": "Ship the TUI",
                    "pending_approvals": [],
                }
                self.first_read_started.set()
                assert self.release_first_read.wait(timeout=2)
                return snapshot
            return super().get_task(task_id)
        finally:
            with self._read_lock:
                self._active_reads -= 1

    def cancel_task(self, task_id: str) -> dict[str, object]:
        response = super().cancel_task(task_id)
        self.release_first_read.set()
        return response

async def enter_run_screen(
    app: CodeAgentTui, pilot: object, before_push: Callable[[], None] | None = None
) -> RunScreen:
    app.task_id = "task-1"
    if before_push is not None:
        before_push()
    app.push_screen(RunScreen(id="run"))
    await pilot.pause()  # type: ignore[attr-defined]
    assert isinstance(app.screen, RunScreen)
    return app.screen


@pytest.mark.asyncio
async def test_default_tui_has_local_api_client_without_requesting_during_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def fail_on_request(client: httpx.Client, request: httpx.Request) -> httpx.Response:
        del client
        requests.append(request)
        raise AssertionError("启动期间不应发起网络请求")

    monkeypatch.setattr(httpx.Client, "send", fail_on_request)
    app = CodeAgentTui()

    assert isinstance(app.client, TaskApiClient)
    assert app.api_base_url == "http://127.0.0.1:8000"
    async with app.run_test() as _pilot:
        assert app.screen.id == "start"
        assert requests == []


@pytest.mark.asyncio
async def test_start_screen_creates_mock_task_and_switches_to_run_screen() -> None:
    client = FakeTaskApiClient()
    app = CodeAgentTui(client=client)

    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.query_one("#workspace", Input)
        assert app.screen.query_one("#goal", Input)
        assert app.screen.query_one("#mode", Input)
        assert app.screen.query_one("#mock-decisions", Input)

        app.screen.query_one("#workspace", Input).value = "C:/repo"
        app.screen.query_one("#goal", Input).value = "Ship the TUI"
        app.screen.query_one("#mode", Input).value = "plan"
        app.screen.query_one("#mock-decisions", Input).value = (
            '[{"action": "complete", "completion_message": "ready"}]'
        )
        await pilot.click("#create-task")
        await pilot.pause()

        assert client.payloads == [
            {
                "workspace": "C:/repo",
                "goal": "Ship the TUI",
                "mode": "plan",
                "provider": "mock",
                "mock_decisions": [
                    {"action": "complete", "completion_message": "ready"}
                ],
            }
        ]
        assert app.task_id == "task-1"
        assert isinstance(app.screen, RunScreen)


@pytest.mark.asyncio
async def test_start_screen_non_mock_provider_omits_mock_decisions() -> None:
    client = FakeTaskApiClient()
    app = CodeAgentTui(client=client)

    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#workspace", Input).value = "C:/repo"
        app.screen.query_one("#goal", Input).value = "Inspect"
        app.screen.query_one("#provider", Input).value = "openai"
        await pilot.click("#create-task")

        assert client.payloads[0]["provider"] == "openai"
        assert "mock_decisions" not in client.payloads[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(("field", "value"), [("#workspace", ""), ("#goal", "")])
async def test_start_screen_requires_workspace_and_goal_before_request(
    field: str, value: str
) -> None:
    client = FakeTaskApiClient()
    app = CodeAgentTui(client=client)
    notifications: list[str] = []
    app.notify = lambda message, **_kwargs: notifications.append(str(message))  # type: ignore[method-assign]

    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#workspace", Input).value = "C:/repo"
        app.screen.query_one("#goal", Input).value = "Ship the TUI"
        app.screen.query_one(field, Input).value = value
        await pilot.click("#create-task")

        assert client.payloads == []
        assert notifications == ["工作目录和目标不能为空"]


@pytest.mark.asyncio
async def test_start_screen_shows_chinese_notification_for_invalid_decisions_json() -> None:
    client = FakeTaskApiClient()
    app = CodeAgentTui(client=client)
    notifications: list[str] = []
    app.notify = lambda message, **_kwargs: notifications.append(str(message))  # type: ignore[method-assign]

    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#workspace", Input).value = "C:/repo"
        app.screen.query_one("#goal", Input).value = "Ship the TUI"
        app.screen.query_one("#mock-decisions", Input).value = "not json"
        await pilot.click("#create-task")

        assert client.payloads == []
        assert notifications == ["模拟决策必须是合法 JSON"]


@pytest.mark.asyncio
async def test_start_screen_shows_chinese_notification_for_api_error() -> None:
    app = CodeAgentTui(client=FailingTaskApiClient())
    notifications: list[str] = []
    app.notify = lambda message, **_kwargs: notifications.append(str(message))  # type: ignore[method-assign]

    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#workspace", Input).value = "C:/repo"
        app.screen.query_one("#goal", Input).value = "Ship the TUI"
        await pilot.click("#create-task")

        assert notifications == ["创建任务失败"]
        assert app.task_id is None


@pytest.mark.asyncio
async def test_run_screen_polls_from_zero_then_appends_only_new_sequences() -> None:
    client = RuntimeTaskApiClient(
        events_for_after={
            0: [
                {"sequence": 1, "type": "started", "payload": {"summary": "开始"}},
                {"sequence": 2, "type": "tool", "payload": {"summary": "测试"}},
            ],
            2: [
                {"sequence": 2, "type": "tool", "payload": {"summary": "重复"}},
                {"sequence": 3, "type": "done", "payload": {"summary": "完成"}},
            ],
        }
    )
    app = CodeAgentTui(client=client)

    async with app.run_test() as pilot:
        screen = await enter_run_screen(app, pilot)
        await screen.refresh_task()

        assert client.event_afters[:2] == [0, 2]
        assert [event["sequence"] for event in app.events] == [1, 2, 3]
        assert app.last_sequence == 3
        assert "完成" in str(screen.query_one("#recent-events", Static).render())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("y", ("approval-1", True, "once")),
        ("a", ("approval-1", True, "task")),
        ("n", ("approval-1", False, "once")),
    ],
)
async def test_approval_keys_submit_decision_and_return_to_run(
    key: str, expected: tuple[str, bool, str]
) -> None:
    client = RuntimeTaskApiClient(status="waiting_approval")
    app = CodeAgentTui(client=client)

    async with app.run_test() as pilot:
        app.task_id = "task-1"
        app.push_screen(RunScreen(id="run"))
        await pilot.pause()
        assert isinstance(app.screen, ApprovalScreen)

        await pilot.press(key)
        await pilot.pause()

        assert client.decisions == [expected]
        assert isinstance(app.screen, RunScreen)


@pytest.mark.asyncio
async def test_cancel_refreshes_immediately_and_routes_to_result() -> None:
    client = RuntimeTaskApiClient()
    app = CodeAgentTui(client=client)

    async with app.run_test() as pilot:
        await enter_run_screen(app, pilot)
        reads_before_cancel = client.task_reads
        await pilot.press("c")
        await pilot.pause()

        assert client.cancel_calls == 1
        assert client.task_reads > reads_before_cancel
        assert isinstance(app.screen, ResultScreen)


@pytest.mark.asyncio
async def test_cancel_during_slow_poll_queues_single_refresh_before_next_interval() -> None:
    client = BlockingCancelTaskApiClient()
    app = CodeAgentTui(client=client)

    async with app.run_test() as pilot:
        app.task_id = "task-1"
        app.push_screen(RunScreen(id="run"))
        assert await asyncio.to_thread(client.first_read_started.wait, 1)
        screen = app.screen
        assert isinstance(screen, RunScreen)

        await screen.action_cancel_task()
        for _ in range(25):
            if isinstance(app.screen, ResultScreen):
                break
            await asyncio.sleep(0.01)

        assert client.cancel_calls == 1
        assert client.task_reads >= 2
        assert client.max_active_reads == 1
        assert isinstance(app.screen, ResultScreen)
        reads_after_leave = client.task_reads
        await pilot.pause(0.55)
        assert client.task_reads == reads_after_leave


@pytest.mark.asyncio
async def test_recovery_required_result_explains_restart_semantics() -> None:
    client = RuntimeTaskApiClient(
        status="needs_review",
        recovery_required=True,
        recovery_reason="服务重启后需人工复核",
        resumable=True,
    )
    app = CodeAgentTui(client=client)

    async with app.run_test() as pilot:
        app.task_id = "task-1"
        app.push_screen(RunScreen(id="run"))
        await pilot.pause()

        assert isinstance(app.screen, ResultScreen)
        assert "服务重启后需人工复核" in str(
            app.screen.query_one("#result-summary", Static).render()
        )
        assert "从头重新执行" in str(
            app.screen.query_one("#recovery-hint", Static).render()
        )


@pytest.mark.asyncio
async def test_restart_recovery_result_can_resume_and_refresh_immediately() -> None:
    client = RuntimeTaskApiClient(
        status="needs_review",
        recovery_required=True,
        recovery_reason="服务重启后需人工复核",
        resumable=True,
    )
    app = CodeAgentTui(client=client)

    async with app.run_test() as pilot:
        app.task_id = "task-1"
        app.push_screen(RunScreen(id="run"))
        await pilot.pause()
        assert isinstance(app.screen, ResultScreen)
        reads_before_resume = client.task_reads

        await pilot.press("r")
        await pilot.pause()

        assert client.resume_calls == 1
        assert client.task_reads > reads_before_resume
        assert isinstance(app.screen, RunScreen)


@pytest.mark.asyncio
async def test_cancelled_result_does_not_resume_without_restart_recovery() -> None:
    client = RuntimeTaskApiClient(status="cancelled")
    app = CodeAgentTui(client=client)

    async with app.run_test() as pilot:
        app.task_id = "task-1"
        app.push_screen(RunScreen(id="run"))
        await pilot.pause()
        assert isinstance(app.screen, ResultScreen)

        await pilot.press("r")
        await pilot.pause()

        assert client.resume_calls == 0
        assert isinstance(app.screen, ResultScreen)


@pytest.mark.asyncio
async def test_poll_error_keeps_cursor_and_next_refresh_continues_from_it() -> None:
    client = RuntimeTaskApiClient(
        events_for_after={
            0: [{"sequence": 4, "type": "started", "payload": {"summary": "开始"}}],
            4: [{"sequence": 5, "type": "done", "payload": {"summary": "继续"}}],
        }
    )
    app = CodeAgentTui(client=client)
    notifications: list[str] = []
    app.notify = lambda message, **_kwargs: notifications.append(str(message))  # type: ignore[method-assign]

    async with app.run_test() as pilot:
        screen = await enter_run_screen(app, pilot)
        client.fail_next_task_read = True
        await screen.refresh_task()

        assert app.last_sequence == 4
        assert isinstance(app.screen, RunScreen)
        assert notifications == ["刷新任务失败"]

        await screen.refresh_task()
        assert client.event_afters[-1] == 4
        assert app.last_sequence == 5


@pytest.mark.asyncio
async def test_terminal_detail_routes_to_result_when_event_refresh_fails() -> None:
    client = RuntimeTaskApiClient(status="succeeded", result_report="任务完成")
    client.fail_event_reads = True
    app = CodeAgentTui(client=client)
    app.events = [
        {"sequence": 4, "type": "checkpoint", "payload": {"summary": "已有事件"}}
    ]
    app.last_sequence = 4
    notifications: list[str] = []
    app.notify = lambda message, **_kwargs: notifications.append(str(message))  # type: ignore[method-assign]

    async with app.run_test() as pilot:
        app.task_id = "task-1"
        app.push_screen(RunScreen(id="run"))
        await pilot.pause()

        assert isinstance(app.screen, ResultScreen)
        assert app.task_detail is not None
        assert app.task_detail["status"] == "succeeded"
        assert app.last_sequence == 4
        assert [event["sequence"] for event in app.events] == [4]
        assert notifications == ["刷新事件失败"]
        rendered = str(app.screen.query_one("#result-content", Static).render())
        assert "任务完成" in rendered
        assert "已有事件" in rendered

        reads_after_result = (client.task_reads, len(client.event_afters))
        await pilot.pause(0.55)
        assert (client.task_reads, len(client.event_afters)) == reads_after_result


@pytest.mark.asyncio
@pytest.mark.parametrize(("action", "message"), [("c", "取消任务失败")])
async def test_run_action_error_only_notifies_and_keeps_screen(
    action: str, message: str
) -> None:
    client = RuntimeTaskApiClient()
    client.fail_cancel = True
    app = CodeAgentTui(client=client)
    notifications: list[str] = []
    app.notify = lambda text, **_kwargs: notifications.append(str(text))  # type: ignore[method-assign]

    async with app.run_test() as pilot:
        await enter_run_screen(app, pilot)
        cursor = app.last_sequence
        await pilot.press(action)
        await pilot.pause()

        assert notifications == [message]
        assert app.last_sequence == cursor
        assert isinstance(app.screen, RunScreen)


@pytest.mark.asyncio
async def test_resume_error_only_notifies_and_keeps_restart_recovery_result() -> None:
    client = RuntimeTaskApiClient(
        status="needs_review",
        recovery_required=True,
        recovery_reason="服务重启后需人工复核",
        resumable=True,
    )
    client.fail_resume = True
    app = CodeAgentTui(client=client)
    notifications: list[str] = []
    app.notify = lambda text, **_kwargs: notifications.append(str(text))  # type: ignore[method-assign]

    async with app.run_test() as pilot:
        app.task_id = "task-1"
        app.push_screen(RunScreen(id="run"))
        await pilot.pause()
        assert isinstance(app.screen, ResultScreen)
        await pilot.press("r")
        await pilot.pause()

        assert notifications == ["恢复任务失败"]
        assert isinstance(app.screen, ResultScreen)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    ["succeeded", "needs_review", "blocked", "failed", "budget_exhausted", "cancelled"],
)
async def test_terminal_status_routes_to_result_with_summary(status: str) -> None:
    client = RuntimeTaskApiClient(
        status=status,
        events_for_after={
            0: [{"sequence": 1, "type": "finished", "payload": {"summary": "检查完成"}}]
        },
        result_report="全部检查通过",
    )
    app = CodeAgentTui(client=client)

    async with app.run_test() as pilot:
        app.task_id = "task-1"
        app.push_screen(RunScreen(id="run"))
        await pilot.pause()

        assert isinstance(app.screen, ResultScreen)
        rendered = str(app.screen.query_one("#result-content", Static).render())
        assert status in rendered
        assert "task-1" in rendered
        assert "全部检查通过" in rendered
        assert "检查完成" in rendered


@pytest.mark.asyncio
async def test_result_uses_fallback_when_server_has_no_report() -> None:
    client = RuntimeTaskApiClient(status="failed")
    app = CodeAgentTui(client=client)

    async with app.run_test() as pilot:
        app.task_id = "task-1"
        app.push_screen(RunScreen(id="run"))
        await pilot.pause()

        rendered = str(app.screen.query_one("#result-content", Static).render())
        assert "服务端未提供结果报告" in rendered
