from __future__ import annotations

from textual.widgets import Static


class StatusBar(Static):
    """Bottom status bar showing aggregate session stats and key hints."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        dock: bottom;
        background: $primary-background;
        color: $text;
        padding: 0 1;
        content-align: left middle;
    }
    """

    def __init__(self) -> None:
        super().__init__("", id="status-bar")
        self.update_stats(0, 0, 0, 0)

    def update_stats(self, total: int, active: int, waiting: int, errors: int) -> None:
        """Update the stats display."""
        self.update(
            f"Sessions: {total} | Active: {active} | Waiting: {waiting} "
            f"| Errors: {errors} | Ctrl+N New | Ctrl+Q Quit"
        )
