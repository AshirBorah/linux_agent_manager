from __future__ import annotations

from textual.widgets import Static


class ToastOverlay(Static):
    """Simple toast notification that auto-dismisses after a timeout."""

    DEFAULT_CSS = """
    ToastOverlay {
        layer: overlay;
        dock: bottom;
        offset-x: -2;
        width: auto;
        max-width: 50;
        min-width: 20;
        height: auto;
        padding: 1 2;
        margin: 1 2;
        background: $surface;
        border: solid $primary;
        content-align: right bottom;
        display: none;
    }
    """

    def __init__(self) -> None:
        super().__init__("", id="toast-overlay")
        self._dismiss_timer = None

    def show_toast(self, title: str, message: str, duration: float = 5) -> None:
        """Show a notification that auto-dismisses after *duration* seconds."""
        # Cancel any pending dismiss timer.
        if self._dismiss_timer is not None:
            self._dismiss_timer.stop()
            self._dismiss_timer = None

        self.update(f"[bold]{title}[/bold]\n{message}")
        self.display = True
        self._dismiss_timer = self.set_timer(duration, self._dismiss)

    def _dismiss(self) -> None:
        """Hide the toast."""
        self.display = False
        self._dismiss_timer = None
