import json
from collections.abc import Iterator
from typing import TYPE_CHECKING, cast

from textual.screen import Screen
from textual.widgets import Button, Input, Label

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
    pass


class ApprovalScreen(Screen[None]):
    pass


class ResultScreen(Screen[None]):
    pass
