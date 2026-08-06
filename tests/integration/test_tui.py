import pytest

from code_agent.tui.app import CodeAgentTui


@pytest.mark.asyncio
async def test_tui_starts_on_start_screen() -> None:
    app = CodeAgentTui(api_base_url=None)
    async with app.run_test() as _pilot:
        assert app.screen.id == "start"
