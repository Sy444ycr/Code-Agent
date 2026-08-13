import pytest
from textual.widgets import Input

from code_agent.tui.app import CodeAgentTui
from code_agent.tui.screens import RunScreen
from tests.integration.test_tui import FakeTaskApiClient


@pytest.mark.asyncio
async def test_tui_provider_input_is_sent_without_mock_payload() -> None:
    client = FakeTaskApiClient()
    app = CodeAgentTui(client=client)

    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#workspace", Input).value = "C:/repo"
        app.screen.query_one("#goal", Input).value = "Inspect"
        app.screen.query_one("#provider", Input).value = "openai"
        await pilot.click("#create-task")
        assert isinstance(app.screen, RunScreen)

    assert client.payloads[0]["provider"] == "openai"
    assert "mock_decisions" not in client.payloads[0]
