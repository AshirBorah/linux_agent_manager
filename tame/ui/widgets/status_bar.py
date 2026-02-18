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
        content-align: center middle;
    }
    """

    def __init__(self) -> None:
        super().__init__("", id="status-bar")
        self._total: int = 0
        self._active: int = 0
        self._waiting: int = 0
        self._errors: int = 0
        self._memory_status: str = ""
        self._refresh_display()

    def update_stats(self, total: int, active: int, waiting: int, errors: int) -> None:
        """Update the stats display."""
        self._total = total
        self._active = active
        self._waiting = waiting
        self._errors = errors
        self._refresh_display()

    def set_memory_status(self, status: str) -> None:
        """Update the memory indicator. Empty string hides it."""
        self._memory_status = status
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Re-render the status bar text."""
        stats = (
            f"Sessions: {self._total} | Active: {self._active} | "
            f"Waiting: {self._waiting} | Errors: {self._errors}"
        )
        keys = (
            "F2 New | F3/F4 \u2190\u2192 | F6 Sidebar | F7/F8 \u25b6/\u23f8"
            " | F9 Rename | C-SPC Cmd | F12 Quit"
        )
        parts = [stats]
        if self._memory_status:
            parts.append(f"[Memory: {self._memory_status}]")
        parts.append(keys)
        self.update("  ".join(parts))
