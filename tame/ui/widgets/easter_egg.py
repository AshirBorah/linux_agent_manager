from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label

COW = """\
        ^__^
        (oo)\\_______
        (__)\\       )\\/\\
            ||----w |
            ||     ||

    Izzy is that you?"""


class EasterEgg(ModalScreen[None]):
    """ASCII cow modal. Dismiss on any key."""

    DEFAULT_CSS = """
    EasterEgg {
        align: center middle;
    }

    EasterEgg #egg-box {
        width: auto;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="egg-box"):
            yield Label(COW)

    def on_key(self, event: events.Key) -> None:
        event.stop()
        self.dismiss(None)
