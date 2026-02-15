from __future__ import annotations

from textual.widgets import Input

from lam.ui.events import InputSubmitted


class InputArea(Input):
    """Text input for sending commands to the active session's PTY."""

    DEFAULT_CSS = """
    InputArea {
        dock: bottom;
        margin: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__(
            placeholder="Type a command...",
            id="input-area",
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Post InputSubmitted and clear the input field."""
        text = event.value.strip()
        if text:
            self.post_message(InputSubmitted(text))
        self.value = ""
