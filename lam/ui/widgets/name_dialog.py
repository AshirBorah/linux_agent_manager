from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label


class NameDialog(ModalScreen[str | None]):
    """Modal dialog that asks for a session name."""

    DEFAULT_CSS = """
    NameDialog {
        align: center middle;
    }

    NameDialog #dialog-box {
        width: 50;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    NameDialog #name-input {
        margin-top: 1;
    }

    NameDialog #hint-label {
        margin-top: 1;
        color: $text-muted;
    }
    """

    def __init__(self, default_name: str) -> None:
        super().__init__()
        self._default_name = default_name

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog-box"):
            yield Label("Session name:")
            yield Input(value=self._default_name, id="name-input")
            yield Label("Enter to confirm, Escape to cancel", id="hint-label")

    def on_mount(self) -> None:
        self.query_one("#name-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        name = event.value.strip()
        self.dismiss(name or self._default_name)

    def key_escape(self) -> None:
        self.dismiss(None)
