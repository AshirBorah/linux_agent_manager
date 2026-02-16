from __future__ import annotations

from textual.message import Message


class SessionStatusChanged(Message):
    """A session's status has changed."""

    def __init__(self, session_id: str, old_status: str, new_status: str) -> None:
        super().__init__()
        self.session_id = session_id
        self.old_status = old_status
        self.new_status = new_status


class SessionCreated(Message):
    """A new session was created."""

    def __init__(self, session_id: str) -> None:
        super().__init__()
        self.session_id = session_id


class SessionDeleted(Message):
    """A session was deleted."""

    def __init__(self, session_id: str) -> None:
        super().__init__()
        self.session_id = session_id


class SessionSelected(Message):
    """User selected a different session."""

    def __init__(self, session_id: str) -> None:
        super().__init__()
        self.session_id = session_id


class NotificationToast(Message):
    """Request to show a toast notification in the UI."""

    def __init__(self, title: str, message: str, severity: str = "information") -> None:
        super().__init__()
        self.title = title
        self.message = message
        self.severity = severity


class SidebarFlash(Message):
    """Request to flash a session entry in the sidebar."""

    def __init__(self, session_id: str) -> None:
        super().__init__()
        self.session_id = session_id
