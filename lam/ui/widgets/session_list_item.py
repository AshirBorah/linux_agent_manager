from __future__ import annotations

from textual.widgets import Static

from lam.session.session import Session
from lam.session.state import SessionState
from lam.ui.events import SessionSelected

STATUS_ICONS: dict[SessionState, str] = {
    SessionState.CREATED: "\u25cb",
    SessionState.STARTING: "\u25cb",
    SessionState.ACTIVE: "\u25cf",
    SessionState.IDLE: "\u25cb",
    SessionState.WAITING: "\u25c9",
    SessionState.PAUSED: "\u23f8",
    SessionState.DONE: "\u2713",
    SessionState.ERROR: "\u2717",
}


class SessionListItem(Static):
    """A single session entry in the sidebar list."""

    DEFAULT_CSS = """
    SessionListItem {
        height: 3;
        padding: 0 1;
        content-align: left middle;
    }

    SessionListItem:hover {
        background: $boost;
    }

    SessionListItem.highlighted {
        background: $accent;
        color: $text;
    }

    SessionListItem.status-active {
        color: $success;
    }

    SessionListItem.status-idle {
        color: $text-muted;
    }

    SessionListItem.status-waiting {
        color: $warning;
    }

    SessionListItem.status-error {
        color: $error;
    }

    SessionListItem.status-done {
        color: $text-disabled;
    }

    SessionListItem.status-paused {
        color: $warning;
    }
    """

    def __init__(self, session_id: str, name: str = "", status: SessionState = SessionState.CREATED) -> None:
        super().__init__("", classes="session-item")
        self.session_id = session_id
        self._session_name = name
        self._status = status
        self._render_content()

    def _render_content(self) -> None:
        icon = STATUS_ICONS.get(self._status, "?")
        label = self._status.value.upper()
        self.update(f"{icon} {self._session_name}  [{label}]")

    def _set_status_class(self, state: SessionState) -> None:
        """Remove old status-* classes, add the current one."""
        for s in SessionState:
            self.remove_class(f"status-{s.value}")
        self.add_class(f"status-{state.value}")

    def update_from_session(self, session: Session) -> None:
        """Refresh display from a Session object."""
        self._session_name = session.name
        self._status = session.status
        self._set_status_class(session.status)
        self._render_content()

    def on_mount(self) -> None:
        self._set_status_class(self._status)

    def on_click(self) -> None:
        self.post_message(SessionSelected(self.session_id))
