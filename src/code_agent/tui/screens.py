import asyncio
import json
from collections.abc import Iterator
from typing import TYPE_CHECKING, Literal, cast

from textual import events
from textual.binding import Binding
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Button, Input, Label, Static
from textual.worker import Worker

from code_agent.tui.api import TaskApiError

if TYPE_CHECKING:
    from code_agent.tui.app import CodeAgentTui


class StartScreen(Screen[None]):
    def compose(self) -> Iterator[Label | Input | Button]:
        yield Label("Workspace")
        yield Input(placeholder="工作目录", id="workspace")
        yield Label("Goal")
        yield Input(placeholder="任务目标", id="goal")
        yield Label("Mode")
        yield Input(value="supervised", id="mode")
        yield Label("Mock decisions (JSON)")
        yield Input(value="[]", id="mock-decisions")
        yield Button("创建 Mock 任务", id="create-task", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "create-task":
            return

        workspace = self.query_one("#workspace", Input).value.strip()
        goal = self.query_one("#goal", Input).value.strip()
        if not workspace or not goal:
            self.app.notify("工作目录和目标不能为空", severity="error")
            return

        try:
            decisions = json.loads(self.query_one("#mock-decisions", Input).value)
        except json.JSONDecodeError:
            self.app.notify("模拟决策必须是合法 JSON", severity="error")
            return
        if not isinstance(decisions, list):
            self.app.notify("模拟决策必须是 JSON 数组", severity="error")
            return

        app = cast("CodeAgentTui", self.app)
        if app.client is None:
            app.notify("任务服务未配置", severity="error")
            return
        payload: dict[str, object] = {
            "workspace": workspace,
            "goal": goal,
            "mode": self.query_one("#mode", Input).value.strip() or "supervised",
            "provider": "mock",
            "mock_decisions": decisions,
        }
        try:
            task = app.client.create_task(payload)
        except TaskApiError:
            app.notify("创建任务失败", severity="error")
            return
        task_id = task.get("id")
        if not isinstance(task_id, str):
            app.notify("创建任务失败", severity="error")
            return
        app.task_id = task_id
        app.last_sequence = 0
        app.task_detail = task
        app.events = []
        app.push_screen(RunScreen(id="run"))


class RunScreen(Screen[None]):
    BINDINGS = [Binding("c", "cancel_task", "取消任务")]

    def __init__(
        self,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._poll_timer: Timer | None = None
        self._poll_worker: Worker[None] | None = None
        self._refreshing = False
        self._refresh_requested = False

    def compose(self) -> Iterator[Static]:
        yield Static("正在读取任务详情……", id="task-status")
        yield Static("暂无事件", id="recent-events")
        yield Static("快捷键：c 取消任务", id="run-help")

    def on_mount(self) -> None:
        self._start_polling()

    def on_screen_resume(self, _event: events.ScreenResume) -> None:
        self._start_polling()

    def on_screen_suspend(self, _event: events.ScreenSuspend) -> None:
        self._stop_polling()

    def on_unmount(self) -> None:
        self._stop_polling()

    def _start_polling(self) -> None:
        if self._poll_timer is None:
            self._poll_timer = self.set_interval(0.5, self._schedule_refresh)
        else:
            self._poll_timer.resume()
        self._schedule_refresh()

    def _stop_polling(self) -> None:
        if self._poll_timer is not None:
            self._poll_timer.pause()
        if self._poll_worker is not None:
            self._poll_worker.cancel()
            self._poll_worker = None

    def _schedule_refresh(self) -> None:
        if self._refreshing or not self.is_current:
            return
        self._poll_worker = self.run_worker(self.refresh_task(), exit_on_error=False)

    async def refresh_task(self) -> None:
        if self._refreshing:
            self._refresh_requested = True
            return
        self._refreshing = True
        try:
            while True:
                self._refresh_requested = False
                await self._refresh_once()
                if not self._refresh_requested or not self.is_current:
                    return
        finally:
            self._refreshing = False

    async def _refresh_once(self) -> None:
        app = cast("CodeAgentTui", self.app)
        if app.client is None or app.task_id is None:
            app.notify("任务服务未配置", severity="error")
            return
        try:
            detail = await asyncio.to_thread(app.client.get_task, app.task_id)
        except TaskApiError:
            app.notify("刷新任务失败", severity="error")
            return

        app.task_detail = detail
        try:
            event_response = await asyncio.to_thread(
                app.client.get_events, app.task_id, app.last_sequence
            )
        except TaskApiError:
            app.notify("刷新事件失败", severity="error")
        else:
            self._append_events(event_response)
        self._render_state()

        status = detail.get("status")
        approval = self._pending_approval(detail)
        if status == "waiting_approval" and approval is not None:
            app.push_screen(ApprovalScreen(approval, id="approval"))
        elif isinstance(status, str) and status in app.TERMINAL_STATUSES:
            app.push_screen(ResultScreen(id="result"))

    def _append_events(self, response: dict[str, object]) -> None:
        app = cast("CodeAgentTui", self.app)
        raw_events = response.get("events")
        if not isinstance(raw_events, list):
            return
        for item in raw_events:
            if not isinstance(item, dict):
                continue
            event = cast(dict[str, object], item)
            sequence = event.get("sequence")
            if isinstance(sequence, int) and sequence > app.last_sequence:
                app.events.append(event)
                app.last_sequence = sequence

    def _render_state(self) -> None:
        app = cast("CodeAgentTui", self.app)
        detail = app.task_detail or {}
        self.query_one("#task-status", Static).update(
            "\n".join(
                [
                    f"任务 ID：{app.task_id or '-'}",
                    f"状态：{detail.get('status', '-')}",
                    f"目标：{detail.get('goal', '-')}",
                ]
            )
        )
        self.query_one("#recent-events", Static).update(_event_summary(app.events))

    @staticmethod
    def _pending_approval(detail: dict[str, object]) -> dict[str, object] | None:
        approvals = detail.get("pending_approvals")
        if not isinstance(approvals, list) or not approvals:
            return None
        approval = approvals[0]
        return cast(dict[str, object], approval) if isinstance(approval, dict) else None

    async def action_cancel_task(self) -> None:
        app = cast("CodeAgentTui", self.app)
        if app.client is None or app.task_id is None:
            return
        try:
            await asyncio.to_thread(app.client.cancel_task, app.task_id)
        except TaskApiError:
            app.notify("取消任务失败", severity="error")
            return
        await self.refresh_task()


class ApprovalScreen(Screen[None]):
    BINDINGS = [
        Binding("y", "allow_once", "允许一次"),
        Binding("a", "allow_task", "本任务允许"),
        Binding("n", "reject", "拒绝"),
    ]

    def __init__(
        self,
        approval: dict[str, object] | None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.approval = approval or {}
        self._submitting = False

    def compose(self) -> Iterator[Static]:
        yield Static(
            "\n".join(
                [
                    "任务等待审批",
                    f"原因：{self.approval.get('reason', '-')}",
                    "快捷键：y 允许一次 / a 本任务允许 / n 拒绝",
                ]
            ),
            id="approval-content",
        )

    async def action_allow_once(self) -> None:
        await self._decide(approved=True, scope="once")

    async def action_allow_task(self) -> None:
        await self._decide(approved=True, scope="task")

    async def action_reject(self) -> None:
        await self._decide(approved=False, scope="once")

    async def _decide(self, *, approved: bool, scope: Literal["once", "task"]) -> None:
        if self._submitting:
            return
        app = cast("CodeAgentTui", self.app)
        approval_id = self.approval.get("id")
        if app.client is None or not isinstance(approval_id, str):
            return
        self._submitting = True
        try:
            await asyncio.to_thread(
                app.client.decide_approval,
                approval_id,
                approved=approved,
                scope=scope,
            )
        except TaskApiError:
            app.notify("提交审批失败", severity="error")
            self._submitting = False
            return
        app.pop_screen()


class ResultScreen(Screen[None]):
    BINDINGS = [Binding("r", "resume_task", "恢复任务")]

    def compose(self) -> Iterator[Static]:
        app = cast("CodeAgentTui", self.app)
        detail = app.task_detail or {}
        report = detail.get("result_report")
        if not isinstance(report, str) or not report.strip():
            report = "服务端未提供结果报告"
        yield Static(
            "\n".join(
                [
                    f"状态：{detail.get('status', '-')}",
                    f"任务 ID：{app.task_id or '-'}",
                    f"结果报告：{report}",
                    "最近事件：",
                    _event_summary(app.events),
                ]
            ),
            id="result-content",
        )

    async def action_resume_task(self) -> None:
        app = cast("CodeAgentTui", self.app)
        detail = app.task_detail or {}
        if detail.get("status") != "cancelled" or app.client is None or app.task_id is None:
            return
        try:
            await asyncio.to_thread(app.client.resume_task, app.task_id)
        except TaskApiError:
            app.notify("恢复任务失败", severity="error")
            return
        app.pop_screen()
        run_screen = cast(RunScreen, app.screen)
        await run_screen.refresh_task()


def _event_summary(events_: list[dict[str, object]]) -> str:
    if not events_:
        return "暂无事件"
    lines: list[str] = []
    for event in events_[-10:]:
        payload = event.get("payload")
        summary: object = None
        if isinstance(payload, dict):
            summary = payload.get("summary") or payload.get("message") or payload.get("reason")
        if summary is None:
            summary = event.get("type", "event")
        lines.append(f"#{event.get('sequence', '?')} {summary}")
    return "\n".join(lines)
