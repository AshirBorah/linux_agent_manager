from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class ConfirmDialog(ModalScreen[bool]):
    """Modal confirmation dialog with Yes/No buttons.

    Requires capital ``Y`` to confirm, making destructive actions harder to
    trigger accidentally.
    """

    DEFAULT_CSS = """
    ConfirmDialog {
        align: center middle;
    }

    ConfirmDialog #dialog-box {
        width: 50;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    ConfirmDialog #dialog-buttons {
        margin-top: 1;
        height: auto;
        align: center middle;
    }

    ConfirmDialog .dialog-btn {
        margin: 0 1;
    }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog-box"):
            yield Label(self._message)
            with Horizontal(id="dialog-buttons"):
                yield Button("\\[Y]es", id="confirm-yes", variant="error", classes="dialog-btn")
                yield Button("\\[n]o", id="confirm-no", variant="primary", classes="dialog-btn")

    def on_mount(self) -> None:
        self.query_one("#confirm-no", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(event.button.id == "confirm-yes")

    def on_key(self, event: events.Key) -> None:
        if event.character == "Y":
            event.stop()
            self.dismiss(True)
        elif event.character == "n":
            event.stop()
            self.dismiss(False)

    def key_escape(self) -> None:
        self.dismiss(False)
