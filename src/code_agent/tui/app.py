from __future__ import annotations

from textual.app import App

from code_agent.tui.api import TaskApiClient
from code_agent.tui.screens import StartScreen


class CodeAgentTui(App[None]):
    def __init__(
        self,
        api_base_url: str | None = None,
        client: TaskApiClient | None = None,
    ) -> None:
        super().__init__()
        self.api_base_url = api_base_url
        self.client = client or (TaskApiClient(api_base_url) if api_base_url else None)
        self.task_id: str | None = None
        self.last_sequence = 0
        self.task_detail: dict[str, object] | None = None
        self.events: list[dict[str, object]] = []

    def on_mount(self) -> None:
        self.push_screen(StartScreen(id="start"))
