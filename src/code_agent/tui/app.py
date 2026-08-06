from __future__ import annotations

from textual.app import App

from code_agent.tui.screens import StartScreen


class CodeAgentTui(App[None]):
    def __init__(self, api_base_url: str | None = None) -> None:
        super().__init__()
        self.api_base_url = api_base_url

    def on_mount(self) -> None:
        self.push_screen(StartScreen(id="start"))
