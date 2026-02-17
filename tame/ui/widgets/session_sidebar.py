from __future__ import annotations

from textual.containers import Vertical, VerticalScroll
from textual.widgets import Button, Input, Label, Static

from tame.session.session import Session
from tame.ui.events import GroupToggled
from tame.ui.widgets.session_list_item import SessionListItem


class GroupHeader(Static):
    """Clickable group header that toggles collapse."""

    DEFAULT_CSS = """
    GroupHeader {
        width: 100%;
        height: 1;
        padding: 0 1;
        background: $surface-darken-1;
        color: $text;
    }

    GroupHeader:hover {
        background: $surface-darken-2;
    }
    """

    def __init__(self, group_name: str) -> None:
        super().__init__()
        self._group_name = group_name
        self._collapsed = False

    def on_mount(self) -> None:
        self._render_label()

    def _render_label(self) -> None:
        arrow = ">" if self._collapsed else "v"
        self.update(f"{arrow} {self._group_name}")

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._render_label()
        self.post_message(GroupToggled(self._group_name, self._collapsed))

    def on_click(self) -> None:
        self.toggle()


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

    SessionSidebar #no-results {
        display: none;
        width: 100%;
        text-align: center;
        color: $text-muted;
        padding: 2 1;
    }

    SessionSidebar #new-session-btn {
        margin: 1;
        width: 100%;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._collapsed_groups: set[str] = set()

    def compose(self):
        yield Input(placeholder="Search sessions...", id="session-search")
        with VerticalScroll(id="session-scroll"):
            yield Label("No matching sessions", id="no-results")
        yield Button("+ New Session", id="new-session-btn", variant="primary")

    def add_session(self, session: Session) -> None:
        """Add a new SessionListItem to the list."""
        item = SessionListItem(
            session_id=session.id,
            name=session.name,
            status=session.status,
        )
        item.id = f"session-item-{session.id}"
        if session.group:
            item.add_class(f"group-{session.group}")
            if session.group in self._collapsed_groups:
                item.display = False
        scroll = self.query_one("#session-scroll", VerticalScroll)
        # If session has a group, ensure group header exists
        if session.group:
            self._ensure_group_header(session.group)
        scroll.mount(item)

    def _ensure_group_header(self, group: str) -> None:
        """Create a group header if one doesn't exist yet."""
        header_id = f"group-header-{group}"
        try:
            self.query_one(f"#{header_id}")
        except Exception:
            header = GroupHeader(group)
            header.id = header_id
            scroll = self.query_one("#session-scroll", VerticalScroll)
            scroll.mount(header, before=0)

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

    def on_group_toggled(self, event: GroupToggled) -> None:
        """Show/hide session items when a group is toggled."""
        if event.collapsed:
            self._collapsed_groups.add(event.group)
        else:
            self._collapsed_groups.discard(event.group)
        for item in self.query(SessionListItem):
            if item.has_class(f"group-{event.group}"):
                item.display = not event.collapsed

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter session list items by the search query."""
        if event.input.id != "session-search":
            return
        query = event.value.strip().lower()
        any_visible = False
        for item in self.query(SessionListItem):
            visible = query == "" or query in item._session_name.lower()
            item.display = visible
            if visible:
                any_visible = True
        # Also filter group headers
        for header in self.query(GroupHeader):
            header.display = query == ""
        no_results = self.query_one("#no-results", Label)
        no_results.display = not any_visible and query != ""
