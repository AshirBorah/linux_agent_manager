from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label

COMMAND_ENTRIES: list[tuple[str, str, str]] = [
    ("c", "new_session", "New Session"),
    ("n", "next_session", "Next Session"),
    ("p", "prev_session", "Previous Session"),
    ("k", "kill_session", "Kill Session"),
    ("s", "toggle_sidebar", "Toggle Sidebar"),
    ("r", "resume_all", "Resume All"),
    ("z", "pause_all", "Pause All"),
    ("x", "clear_notifications", "Clear Notifications"),
    ("m", "rename_session", "Rename Session"),
    ("q", "quit", "Quit"),
]


class CommandPalette(ModalScreen[str | None]):
    """Centered overlay showing available command-mode shortcuts.

    Dismisses with the action name when a valid key is pressed,
    or ``None`` on Escape / Ctrl+Space.
    """

    DEFAULT_CSS = """
    CommandPalette {
        align: center middle;
    }

    CommandPalette #cmd-box {
        width: 40;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    CommandPalette .cmd-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    CommandPalette .cmd-row {
        margin: 0;
    }

    CommandPalette .cmd-footer {
        margin-top: 1;
        text-align: center;
        color: $text-muted;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._key_map: dict[str, str] = {key: action for key, action, _ in COMMAND_ENTRIES}

    def compose(self) -> ComposeResult:
        with Vertical(id="cmd-box"):
            yield Label("[bold]Command Mode[/bold]", classes="cmd-title")
            for key, _action, label in COMMAND_ENTRIES:
                yield Label(f"  [bold]{key}[/bold]   {label}", classes="cmd-row")
            yield Label("ESC / C-SPC  cancel", classes="cmd-footer")

    def on_key(self, event: events.Key) -> None:
        event.stop()
        if event.key == "escape" or event.key in ("ctrl+@", "ctrl+space"):
            self.dismiss(None)
            return
        char = event.character
        if char and char in self._key_map:
            self.dismiss(self._key_map[char])
