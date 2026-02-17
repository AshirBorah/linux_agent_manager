from __future__ import annotations

import re

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static


class SearchResult(Static):
    """A single search result entry."""

    DEFAULT_CSS = """
    SearchResult {
        width: 100%;
        height: auto;
        padding: 0 1;
    }

    SearchResult:hover {
        background: $surface-darken-2;
    }
    """

    def __init__(self, session_id: str, session_name: str, line: str, line_num: int) -> None:
        super().__init__()
        self.session_id = session_id
        self._session_name = session_name
        self._line = line
        self._line_num = line_num

    def on_mount(self) -> None:
        # Truncate long lines for display
        display_line = self._line[:120] + "..." if len(self._line) > 120 else self._line
        self.update(f"[bold]{self._session_name}[/bold]:{self._line_num}  {display_line}")

    def on_click(self) -> None:
        # Dismiss with the session_id to switch to it
        screen = self.screen
        if isinstance(screen, SearchDialog):
            screen.dismiss(self.session_id)


# ANSI escape stripper
_ANSI_RE = re.compile(
    r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x1B\x07]*(?:\x07|\x1B\\))"
)


class SearchDialog(ModalScreen[str | None]):
    """Global search across all session output buffers."""

    DEFAULT_CSS = """
    SearchDialog {
        align: center middle;
    }

    SearchDialog #search-box {
        width: 80;
        height: 30;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    SearchDialog #search-input {
        margin-bottom: 1;
    }

    SearchDialog #search-results {
        height: 1fr;
    }

    SearchDialog #result-count {
        height: 1;
        color: $text-muted;
    }
    """

    def __init__(self, sessions: list[tuple[str, str, str]]) -> None:
        """sessions: list of (session_id, session_name, output_text)."""
        super().__init__()
        self._sessions = sessions

    def compose(self) -> ComposeResult:
        with Vertical(id="search-box"):
            yield Label("Search all sessions:")
            yield Input(placeholder="Type to search...", id="search-input")
            yield Label("", id="result-count")
            with VerticalScroll(id="search-results"):
                pass

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "search-input":
            return
        query = event.value.strip()
        scroll = self.query_one("#search-results", VerticalScroll)
        # Remove old results
        for child in list(scroll.children):
            child.remove()
        if not query:
            self.query_one("#result-count", Label).update("")
            return
        results = self._search(query)
        count_label = self.query_one("#result-count", Label)
        count_label.update(f"{len(results)} result(s)")
        for result in results[:100]:  # cap at 100 results
            scroll.mount(result)

    def _search(self, query: str) -> list[SearchResult]:
        results: list[SearchResult] = []
        query_lower = query.lower()
        for session_id, session_name, output_text in self._sessions:
            clean = _ANSI_RE.sub("", output_text)
            for i, line in enumerate(clean.split("\n"), 1):
                if query_lower in line.lower():
                    results.append(
                        SearchResult(session_id, session_name, line.strip(), i)
                    )
        return results

    def key_escape(self) -> None:
        self.dismiss(None)
