from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Label


class HistoryPicker(ModalScreen[str | None]):
    """Modal overlay showing recent input history across sessions.

    Dismisses with the selected command string, or ``None`` on Escape.
    """

    DEFAULT_CSS = """
    HistoryPicker {
        align: center middle;
    }

    HistoryPicker #hist-box {
        width: 60;
        max-height: 20;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    HistoryPicker .hist-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    HistoryPicker .hist-row {
        margin: 0;
    }

    HistoryPicker .hist-row-selected {
        margin: 0;
        background: $primary;
        color: $text;
    }

    HistoryPicker .hist-footer {
        margin-top: 1;
        text-align: center;
        color: $text-muted;
    }

    HistoryPicker .hist-empty {
        text-align: center;
        color: $text-muted;
    }
    """

    def __init__(self, entries: list[str]) -> None:
        super().__init__()
        # Deduplicate preserving most-recent-first order
        seen: set[str] = set()
        unique: list[str] = []
        for entry in reversed(entries):
            if entry not in seen:
                seen.add(entry)
                unique.append(entry)
        self._entries = unique[:50]  # cap display at 50
        self._selected = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="hist-box"):
            yield Label("[bold]Input History[/bold]", classes="hist-title")
            if not self._entries:
                yield Label("No history yet", classes="hist-empty")
            else:
                with VerticalScroll(id="hist-scroll"):
                    for i, entry in enumerate(self._entries):
                        truncated = entry if len(entry) <= 52 else entry[:49] + "..."
                        cls = "hist-row-selected" if i == 0 else "hist-row"
                        yield Label(
                            f" {truncated}",
                            classes=cls,
                            id=f"hist-{i}",
                        )
            yield Label("Up/Down select | Enter run | ESC cancel", classes="hist-footer")

    def _update_highlight(self) -> None:
        for i in range(len(self._entries)):
            try:
                lbl = self.query_one(f"#hist-{i}", Label)
                if i == self._selected:
                    lbl.set_classes("hist-row-selected")
                else:
                    lbl.set_classes("hist-row")
            except Exception:
                pass
        # Scroll selected into view
        try:
            lbl = self.query_one(f"#hist-{self._selected}", Label)
            lbl.scroll_visible()
        except Exception:
            pass

    def on_key(self, event: events.Key) -> None:
        event.stop()
        if event.key == "escape":
            self.dismiss(None)
            return
        if not self._entries:
            return
        if event.key == "up":
            self._selected = max(0, self._selected - 1)
            self._update_highlight()
        elif event.key == "down":
            self._selected = min(len(self._entries) - 1, self._selected + 1)
            self._update_highlight()
        elif event.key in ("enter", "return"):
            self.dismiss(self._entries[self._selected])
