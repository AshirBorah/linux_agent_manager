from __future__ import annotations

from rich.text import Text
from textual import events
from textual.widgets import Static

from tame.session.session import Session
from tame.session.state import SessionState
from tame.ui.events import SessionSelected

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

STATUS_STYLE: dict[SessionState, str] = {
    SessionState.ACTIVE: "green",
    SessionState.IDLE: "dim",
    SessionState.WAITING: "yellow",
    SessionState.ERROR: "red bold",
    SessionState.DONE: "dim",
    SessionState.PAUSED: "yellow",
}

ATTENTION_BADGE: dict[SessionState, tuple[str, str]] = {
    SessionState.WAITING: (" \u25cf", "bold yellow"),
    SessionState.ERROR: (" !", "bold red"),
}


class SessionListItem(Static):
    """A single session entry in the sidebar list."""

    DEFAULT_CSS = """
    SessionListItem.session-item {
        height: 1;
        min-height: 1;
        padding: 0 1;
        content-align: left middle;
        color: $text;
    }

    SessionListItem:hover {
        background: $boost;
    }

    SessionListItem.highlighted {
        background: $accent;
        color: $text;
    }
    """

    def __init__(self, session_id: str, name: str = "", status: SessionState = SessionState.CREATED) -> None:
        super().__init__(classes="session-item")
        self.session_id = session_id
        self._session_name = name
        self._status = status

    def render(self) -> Text:
        """Render session row text directly each paint for reliability."""
        icon = STATUS_ICONS.get(self._status, "?")
        label = self._status.value.upper()
        style = STATUS_STYLE.get(self._status, "")
        name_style = self._name_style()
        line = Text()
        line.append(f"{icon} ", style=style)
        line.append(self._session_name, style=name_style)
        line.append(f"  {label}", style=style)
        badge = ATTENTION_BADGE.get(self._status)
        if badge:
            line.append(badge[0], style=badge[1])
        return line

    def _name_style(self) -> str:
        """Use explicit high-contrast session-name color for readability."""
        try:
            if self.app.dark:
                return "bold #f5f5f5"
            return "bold #1f1f1f"
        except Exception:
            return "bold"

    def update_from_session(self, session: Session) -> None:
        """Refresh display from a Session object."""
        self._session_name = session.name
        self._status = session.status
        self.refresh()

    def on_click(self, event: events.Click) -> None:
        event.stop()
        self.post_message(SessionSelected(self.session_id))
