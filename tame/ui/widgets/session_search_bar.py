from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Input, Label

from tame.ui.events import SearchDismissed, SearchNavigate, SearchQueryChanged


class SessionSearchBar(Widget):
    """Inline search bar for within-session text search.

    Docked at the bottom of the right panel, hidden by default.
    """

    DEFAULT_CSS = """
    SessionSearchBar {
        dock: bottom;
        height: 3;
        background: $surface;
        border-top: solid $primary;
        display: none;
    }

    SessionSearchBar.visible {
        display: block;
    }

    SessionSearchBar #search-row {
        height: 3;
        padding: 0 1;
    }

    SessionSearchBar #session-search-input {
        width: 1fr;
    }

    SessionSearchBar #match-count {
        width: auto;
        min-width: 10;
        padding: 0 1;
        content-align: center middle;
    }

    SessionSearchBar .search-btn {
        min-width: 3;
        width: 3;
    }
    """

    is_regex: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        with Horizontal(id="search-row"):
            yield Input(placeholder="Search in session...", id="session-search-input")
            yield Label("0/0", id="match-count")
            yield Button("<", id="prev-match", classes="search-btn")
            yield Button(">", id="next-match", classes="search-btn")

    def show(self) -> None:
        self.add_class("visible")
        self.query_one("#session-search-input", Input).focus()

    def hide(self) -> None:
        self.remove_class("visible")
        self.query_one("#session-search-input", Input).value = ""
        self.post_message(SearchDismissed())

    @property  # type: ignore[misc]
    def visible(self) -> bool:
        return self.has_class("visible")

    def update_match_count(self, current: int, total: int) -> None:
        label = self.query_one("#match-count", Label)
        if total == 0:
            label.update("0/0")
        else:
            label.update(f"{current + 1}/{total}")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "session-search-input":
            return
        query = event.value
        self.post_message(SearchQueryChanged(query, self.is_regex))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "prev-match":
            self.post_message(SearchNavigate(forward=False))
        elif event.button.id == "next-match":
            self.post_message(SearchNavigate(forward=True))

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.hide()
            event.stop()
        elif event.key == "enter":
            self.post_message(SearchNavigate(forward=True))
            event.stop()
        elif event.key == "shift+enter":
            self.post_message(SearchNavigate(forward=False))
            event.stop()
        elif event.key == "alt+r":
            self.is_regex = not self.is_regex
            query = self.query_one("#session-search-input", Input).value
            self.post_message(SearchQueryChanged(query, self.is_regex))
            event.stop()
