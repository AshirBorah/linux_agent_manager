from __future__ import annotations

from textual.widgets import Static

from lam.session.session import Session


class HeaderBar(Static):
    """Compact single-line top bar: app title, session info, and system stats."""

    DEFAULT_CSS = """
    HeaderBar {
        height: 1;
        dock: top;
        padding: 0 1;
        background: $primary-background;
        color: $text;
        content-align: left middle;
    }
    """

    def __init__(self) -> None:
        super().__init__("LAM", id="header-bar")
        self._session_info: str = ""
        self._system_stats: str = ""
        self._refresh_content()

    def update_from_session(self, session: Session) -> None:
        """Show session name, status, and PID inline."""
        from lam.session.state import SessionState

        status_icons = {
            SessionState.ACTIVE: "\u25cf ACTIVE",
            SessionState.IDLE: "\u25cb IDLE",
            SessionState.WAITING: "\u25c9 WAITING",
            SessionState.ERROR: "\u2717 ERROR",
            SessionState.DONE: "\u2713 DONE",
            SessionState.PAUSED: "\u23f8 PAUSED",
        }
        status = status_icons.get(session.status, session.status.value)
        pid_str = str(session.pid) if session.pid is not None else "-"
        self._session_info = f"{session.name} | {status} | PID {pid_str}"
        self._refresh_content()

    def clear_session(self) -> None:
        """Reset to no-session state."""
        self._session_info = ""
        self._refresh_content()

    def update_system_stats(self, cpu_percent: float, memory_used: str) -> None:
        """Update the system resource display."""
        self._system_stats = f"CPU:{cpu_percent:.0f}% {memory_used}"
        self._refresh_content()

    def _refresh_content(self) -> None:
        parts = ["LAM"]
        if self._session_info:
            parts.append(self._session_info)
        if self._system_stats:
            parts.append(self._system_stats)
        self.update(" | ".join(parts))
