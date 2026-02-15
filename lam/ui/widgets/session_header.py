from __future__ import annotations

from datetime import datetime, timezone

from textual.widgets import Static

from lam.session.session import Session


class SessionHeader(Static):
    """Info bar above the session viewer showing session metadata."""

    DEFAULT_CSS = """
    SessionHeader {
        height: 3;
        padding: 0 1;
        background: $primary-background;
        color: $text;
        content-align: left middle;
    }
    """

    def __init__(self) -> None:
        super().__init__("No session selected", id="session-header")

    def update_from_session(self, session: Session) -> None:
        """Refresh the header with current session info."""
        pid_str = str(session.pid) if session.pid is not None else "-"
        age = _format_age(session.last_activity)
        self.update(
            f"{session.name}  |  {session.working_dir}  |  PID {pid_str}  |  {age}"
        )


def _format_age(last_activity: datetime) -> str:
    """Human-readable time since *last_activity*."""
    now = datetime.now(timezone.utc) if last_activity.tzinfo else datetime.now()
    delta = now - last_activity
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        return "just now"
    if total_seconds < 60:
        return f"{total_seconds}s ago"
    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    return f"{hours}h {minutes % 60}m ago"
