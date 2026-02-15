from __future__ import annotations

from textual.containers import Horizontal
from textual.widgets import Button, Static


class HeaderBar(Horizontal):
    """Top bar showing app title, global actions, and system resource summary."""

    DEFAULT_CSS = """
    HeaderBar {
        height: 3;
        dock: top;
        padding: 0 1;
        background: $primary-background;
        color: $text;
    }

    HeaderBar .title {
        width: 1fr;
        content-align: left middle;
        padding: 0 1;
    }

    HeaderBar Button {
        min-width: 14;
        margin: 0 1;
    }

    HeaderBar .system-stats {
        width: auto;
        content-align: right middle;
        padding: 0 1;
    }
    """

    def compose(self):
        yield Static("LAM  Linux Agent Manager", classes="title")
        yield Button("\u25b6 Resume All", id="resume-all", variant="success")
        yield Button("\u23f8 Pause All", id="pause-all", variant="warning")
        yield Static("", id="system-stats", classes="system-stats")

    def update_system_stats(self, cpu_percent: float, memory_used: str) -> None:
        """Update the system resource display."""
        stats = self.query_one("#system-stats", Static)
        stats.update(f"CPU:{cpu_percent:.0f}% {memory_used}")
