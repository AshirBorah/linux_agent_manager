from __future__ import annotations

from rich.text import Text
from textual.widgets import RichLog

from lam.session.output_buffer import OutputBuffer


class SessionViewer(RichLog):
    """Main output display for the currently active session."""

    DEFAULT_CSS = """
    SessionViewer {
        height: 1fr;
        border: solid $primary;
    }
    """

    def __init__(self) -> None:
        super().__init__(
            highlight=False,
            markup=False,
            wrap=True,
            auto_scroll=True,
            id="session-viewer",
        )

    def append_output(self, text: str) -> None:
        """Write ANSI-containing text to the log."""
        rich_text = Text.from_ansi(text)
        self.write(rich_text)

    def load_buffer(self, output_buffer: OutputBuffer) -> None:
        """Clear and reload all lines from a buffer (used when switching sessions)."""
        self.clear()
        for line in output_buffer.get_lines():
            rich_text = Text.from_ansi(line)
            self.write(rich_text)
