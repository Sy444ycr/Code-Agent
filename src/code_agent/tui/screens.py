from collections.abc import Iterator

from textual.screen import Screen
from textual.widgets import Label


class StartScreen(Screen[None]):
    def compose(self) -> Iterator[Label]:
        yield Label("Workspace")
        yield Label("Goal")


class RunScreen(Screen[None]):
    pass


class ApprovalScreen(Screen[None]):
    pass


class ResultScreen(Screen[None]):
    pass
