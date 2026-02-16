from __future__ import annotations

import re
from functools import lru_cache

from rich.style import Style
from rich.text import Text
from textual import events
from textual.timer import Timer
from textual.widget import Widget

from tame.session.output_buffer import OutputBuffer

try:
    import pyte
except Exception:  # pragma: no cover - fallback for environments missing pyte
    pyte = None  # type: ignore[assignment]


_FG_COLOR_MAP: dict[str, str] = {
    "default": "default",
    "black": "black",
    "red": "red",
    "green": "green",
    "brown": "yellow",
    "blue": "blue",
    "magenta": "magenta",
    "cyan": "cyan",
    "white": "white",
    "brightblack": "bright_black",
    "brightred": "bright_red",
    "brightgreen": "bright_green",
    "brightbrown": "bright_yellow",
    "brightblue": "bright_blue",
    "brightmagenta": "bright_magenta",
    "brightcyan": "bright_cyan",
    "brightwhite": "bright_white",
}

_BG_COLOR_MAP: dict[str, str] = {
    **_FG_COLOR_MAP,
    "default": "",
}

_HEX_COLOR_RE = re.compile(r"^[0-9a-fA-F]{6}$")


def _normalize_color(name: str) -> str:
    """Prepend '#' to bare hex color strings so Rich can parse them."""
    if _HEX_COLOR_RE.match(name):
        return f"#{name}"
    return name


class _TerminalState:
    """Cached pyte terminal state for a single session."""

    __slots__ = ("session_id", "screen", "stream")

    def __init__(self, session_id: str, rows: int, cols: int) -> None:
        self.session_id = session_id
        self.screen = pyte.HistoryScreen(columns=cols, lines=rows, history=10000)
        self.stream = pyte.Stream(self.screen)

    def feed(self, text: str) -> None:
        self.stream.feed(text)

    def resize(self, rows: int, cols: int) -> None:
        self.screen.resize(lines=rows, columns=cols)


class SessionViewer(Widget):
    """PTY-backed terminal viewport for the currently active session."""

    can_focus = True

    DEFAULT_CSS = """
    SessionViewer {
        height: 1fr;
        width: 1fr;
        background: $background;
        color: $text;
    }
    """

    # Target ≤60 UI updates/sec per session
    _RENDER_INTERVAL: float = 1.0 / 60

    def __init__(self) -> None:
        super().__init__(id="session-viewer")
        self._fallback_text: str = ""
        self._rows: int = 24
        self._cols: int = 80
        self._has_session: bool = False
        self._terminals: dict[str, _TerminalState] = {}
        self._active_terminal: _TerminalState | None = None
        self._scroll_offset: int = 0  # 0 = at bottom
        self._auto_scroll: bool = True
        self._dirty: bool = False
        self._refresh_timer: Timer | None = None

    def append_output(self, text: str) -> None:
        """Feed new PTY output into terminal state and schedule a refresh."""
        if not text:
            return

        if self._active_terminal is None:
            self._fallback_text += text
            self._schedule_refresh()
            return

        self._active_terminal.feed(text)
        if self._auto_scroll:
            self._scroll_offset = 0
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        """Coalesce rapid refresh requests into at most 60/sec."""
        if self._dirty:
            return  # Already scheduled
        self._dirty = True
        self._refresh_timer = self.set_timer(
            self._RENDER_INTERVAL, self._flush_refresh, name="viewer_refresh"
        )

    def _flush_refresh(self) -> None:
        """Flush a pending refresh."""
        self._dirty = False
        self._refresh_timer = None
        self.refresh()

    def load_session(self, session_id: str, output_buffer: OutputBuffer) -> None:
        """Switch to a session, replaying its buffer only on first visit."""
        self._has_session = True
        self._scroll_offset = 0
        self._auto_scroll = True

        if pyte is None:
            self._fallback_text = output_buffer.get_all_text()
            self.refresh()
            return

        if session_id in self._terminals:
            # Already cached — instant swap
            self._active_terminal = self._terminals[session_id]
            self.refresh()
            return

        # First visit — create terminal state and replay buffer
        rows = max(1, self.size.height or self._rows)
        cols = max(1, self.size.width or self._cols)
        terminal = _TerminalState(session_id, rows, cols)
        full_text = output_buffer.get_all_text()
        if full_text:
            terminal.feed(full_text)
        self._terminals[session_id] = terminal
        self._active_terminal = terminal
        self.refresh()

    def load_buffer(self, output_buffer: OutputBuffer) -> None:
        """Legacy method — reset terminal state and replay buffer contents.

        Kept for backward compatibility with tests and callers that don't
        track session IDs.
        """
        self._has_session = True
        full_text = output_buffer.get_all_text()
        if pyte is None:
            self._fallback_text = full_text
            self.refresh()
            return

        rows = max(1, self.size.height or self._rows)
        cols = max(1, self.size.width or self._cols)
        terminal = _TerminalState("__legacy__", rows, cols)
        if full_text:
            terminal.feed(full_text)
        self._terminals["__legacy__"] = terminal
        self._active_terminal = terminal
        self.refresh()

    def feed_session(self, session_id: str, text: str) -> None:
        """Feed output into a background session's cached terminal."""
        if not text:
            return
        terminal = self._terminals.get(session_id)
        if terminal is not None:
            terminal.feed(text)

    def remove_session(self, session_id: str) -> None:
        """Discard cached terminal state for a deleted session."""
        terminal = self._terminals.pop(session_id, None)
        if self._active_terminal is terminal and terminal is not None:
            self._active_terminal = None
            self._has_session = bool(self._terminals)
            self.refresh()

    def on_resize(self, event: events.Resize) -> None:
        rows = max(1, event.size.height)
        cols = max(1, event.size.width)
        self._rows = rows
        self._cols = cols

        for terminal in self._terminals.values():
            terminal.resize(rows, cols)

        self.refresh()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        """Scroll up through history."""
        history_len = (
            len(self._active_terminal.screen.history.top)
            if self._active_terminal
            else 0
        )
        if history_len > 0:
            self._scroll_offset = min(self._scroll_offset + 3, history_len)
            self._auto_scroll = False
            self.refresh()

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        """Scroll down toward live output."""
        self._scroll_offset = max(0, self._scroll_offset - 3)
        if self._scroll_offset == 0:
            self._auto_scroll = True
        self.refresh()

    def render(self) -> Text:
        if not self._has_session:
            return self._render_welcome()
        if self._active_terminal is None:
            return Text.from_ansi(self._fallback_text)
        return self._render_terminal_text()

    def _render_welcome(self) -> Text:
        """Render branded welcome screen when no sessions exist."""
        w = max(1, self.size.width or 80)
        h = max(1, self.size.height or 24)

        logo = [
            " _____ _   __  __ ___",
            "|_   _/_\\ |  \\/  | __|",
            "  | |/ _ \\| |\\/| | _|",
            "  |_/_/ \\_\\_|  |_|___|",
        ]
        subtitle = "Terminal Agent Management Environment"
        version = "v0.1.0"
        shortcuts = [
            ("Ctrl+Space", "Open Command Palette"),
            ("  c", "New Session"),
            ("  n / p", "Next / Prev Session"),
            ("  k", "Kill Session"),
            ("  s", "Toggle Sidebar"),
            ("  q", "Quit"),
        ]

        lines: list[str] = []
        # vertical centering
        content_height = len(logo) + 2 + 1 + 1 + len(shortcuts) + 2
        top_pad = max(0, (h - content_height) // 2)
        lines.extend([""] * top_pad)

        # logo
        for row in logo:
            lines.append(row.center(w))
        lines.append("")

        # subtitle + version
        lines.append(subtitle.center(w))
        lines.append(version.center(w))
        lines.append("")

        # shortcuts
        for key, action in shortcuts:
            entry = f"  {key:<16}{action}"
            lines.append(entry.center(w))

        lines.append("")
        hint = "Tame your AI agents."
        lines.append(hint.center(w))

        output = Text()
        for i, line in enumerate(lines):
            output.append(line)
            if i < len(lines) - 1:
                output.append("\n")
        return output

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _render_terminal_text(self) -> Text:
        assert self._active_terminal is not None
        screen = self._active_terminal.screen
        rows = max(1, self._rows)
        cols = max(1, self._cols)

        output = Text()

        if self._scroll_offset > 0:
            # Render from scrollback history
            history_lines = list(screen.history.top)
            total_history = len(history_lines)

            # Calculate which lines to show
            start = max(0, total_history - self._scroll_offset)

            # Mix history lines and screen lines
            visible_lines: list[dict] = []
            for i in range(start, min(start + rows, total_history)):
                visible_lines.append(history_lines[i])

            remaining = rows - len(visible_lines)
            if remaining > 0:
                for y in range(min(remaining, rows)):
                    visible_lines.append(screen.buffer.get(y, {}))

            for y_idx, row in enumerate(visible_lines[:rows]):
                for x in range(cols):
                    char = row.get(x)
                    symbol = " " if char is None else (char.data or " ")
                    style = self._char_style(char)
                    output.append(symbol, style=style)
                if y_idx < rows - 1:
                    output.append("\n")
        else:
            # Normal rendering (at bottom)
            buffer = screen.buffer
            cursor = screen.cursor
            cursor_x = getattr(cursor, "x", -1)
            cursor_y = getattr(cursor, "y", -1)
            cursor_hidden = bool(getattr(cursor, "hidden", False))
            has_focus = self.has_focus

            for y in range(rows):
                row = buffer.get(y, {})
                for x in range(cols):
                    char = row.get(x)
                    symbol = " " if char is None else (char.data or " ")
                    style = self._char_style(char)
                    if (
                        has_focus
                        and not cursor_hidden
                        and x == cursor_x
                        and y == cursor_y
                    ):
                        style += Style(reverse=True)
                    output.append(symbol, style=style)
                if y < rows - 1:
                    output.append("\n")

        return output

    @staticmethod
    @lru_cache(maxsize=1024)
    def _style_from_attrs(
        fg: str,
        bg: str,
        bold: bool,
        italics: bool,
        underscore: bool,
        strikethrough: bool,
        reverse: bool,
    ) -> Style:
        fg_name = _normalize_color(_FG_COLOR_MAP.get(fg, fg))
        bg_name = _normalize_color(_BG_COLOR_MAP.get(bg, bg))
        if reverse:
            fg_name, bg_name = (bg_name or "default"), fg_name
        return Style(
            color=fg_name if fg_name and fg_name != "default" else None,
            bgcolor=bg_name if bg_name and bg_name != "default" else None,
            bold=bold,
            italic=italics,
            underline=underscore,
            strike=strikethrough,
        )

    def _char_style(self, char) -> Style:
        if char is None:
            return Style()
        return self._style_from_attrs(
            str(getattr(char, "fg", "default")),
            str(getattr(char, "bg", "default")),
            bool(getattr(char, "bold", False)),
            bool(getattr(char, "italics", False)),
            bool(getattr(char, "underscore", False)),
            bool(getattr(char, "strikethrough", False)),
            bool(getattr(char, "reverse", False)),
        )
