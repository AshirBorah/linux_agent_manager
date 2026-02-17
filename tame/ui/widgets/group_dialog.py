from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label


class GroupDialog(ModalScreen[str | None]):
    """Modal dialog to set a session's group name."""

    DEFAULT_CSS = """
    GroupDialog {
        align: center middle;
    }

    GroupDialog #dialog-box {
        width: 50;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    GroupDialog #group-input {
        margin-top: 1;
    }

    GroupDialog #hint-label {
        margin-top: 1;
        color: $text-muted;
    }
    """

    def __init__(self, current_group: str = "") -> None:
        super().__init__()
        self._current_group = current_group

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog-box"):
            yield Label("Group name (empty to ungroup):")
            yield Input(value=self._current_group, id="group-input")
            yield Label("Enter to confirm, Escape to cancel", id="hint-label")

    def on_mount(self) -> None:
        self.query_one("#group-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.dismiss(event.value.strip())

    def key_escape(self) -> None:
        self.dismiss(None)
