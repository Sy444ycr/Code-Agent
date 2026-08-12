import pytest
from textual.widgets import Input

from code_agent.tui.api import TaskApiError
from code_agent.tui.app import CodeAgentTui
from code_agent.tui.screens import RunScreen


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


@pytest.mark.asyncio
async def test_tui_starts_on_start_screen() -> None:
    app = CodeAgentTui(api_base_url=None)
    async with app.run_test() as _pilot:
        assert app.screen.id == "start"


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
