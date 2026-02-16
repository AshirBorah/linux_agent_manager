from __future__ import annotations

from textual.containers import Vertical, VerticalScroll
from textual.widgets import Button, Input

from tame.session.session import Session
from tame.ui.widgets.session_list_item import SessionListItem


class SessionSidebar(Vertical):
    """Left sidebar containing session search, session list, and new-session button."""

    DEFAULT_CSS = """
    SessionSidebar {
        width: 32;
        dock: left;
        background: $surface;
        border-right: solid $primary;
    }

    SessionSidebar #session-search {
        margin: 1;
    }

    SessionSidebar #session-scroll {
        height: 1fr;
    }

    SessionSidebar #new-session-btn {
        margin: 1;
        width: 100%;
    }
    """

    def compose(self):
        yield Input(placeholder="Search sessions...", id="session-search")
        yield VerticalScroll(id="session-scroll")
        yield Button("+ New Session", id="new-session-btn", variant="primary")

    def add_session(self, session: Session) -> None:
        """Add a new SessionListItem to the list."""
        item = SessionListItem(
            session_id=session.id,
            name=session.name,
            status=session.status,
        )
        item.id = f"session-item-{session.id}"
        scroll = self.query_one("#session-scroll", VerticalScroll)
        scroll.mount(item)

    def remove_session(self, session_id: str) -> None:
        """Remove a session item by its session_id."""
        try:
            item = self.query_one(f"#session-item-{session_id}", SessionListItem)
            item.remove()
        except Exception:
            pass

    def update_session(self, session: Session) -> None:
        """Update an existing session item."""
        try:
            item = self.query_one(f"#session-item-{session.id}", SessionListItem)
            item.update_from_session(session)
        except Exception:
            pass

    def highlight_session(self, session_id: str) -> None:
        """Visually highlight the given session and un-highlight others."""
        for item in self.query(SessionListItem):
            if item.session_id == session_id:
                item.add_class("highlighted")
            else:
                item.remove_class("highlighted")

    def clear_all_flash(self) -> None:
        """Remove the flash class from all session items."""
        for item in self.query(SessionListItem):
            item.remove_class("flash")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter session list items by the search query."""
        if event.input.id != "session-search":
            return
        query = event.value.strip().lower()
        for item in self.query(SessionListItem):
            if query == "" or query in item._session_name.lower():
                item.display = True
            else:
                item.display = False
