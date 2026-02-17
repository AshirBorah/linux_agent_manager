from __future__ import annotations

import logging
import re
from collections import defaultdict
from functools import lru_cache

from rich.style import Style
from rich.text import Text
from textual import events
from textual.timer import Timer
from textual.widget import Widget

from tame.session.output_buffer import OutputBuffer
from tame.ui.events import ViewerResized

log = logging.getLogger("tame.viewer")

try:
    import pyte
    from pyte.screens import StaticDefaultDict
    _PYTE_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - fallback for environments missing pyte
    pyte = None  # type: ignore[assignment]
    StaticDefaultDict = None  # type: ignore[assignment,misc]
    _PYTE_IMPORT_ERROR = exc


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
_FALLBACK_FULL_CLEAR_RE = re.compile(
    r"\x0c|\x1bc|\x1b\[(?:2|3)J|\x1b\[(?:H|1;1H|1;H|;1H|;H)\x1b\[(?:0)?J"
)


def _normalize_color(name: str) -> str:
    """Prepend '#' to bare hex color strings so Rich can parse them."""
    if _HEX_COLOR_RE.match(name):
        return f"#{name}"
    return name


class TAMEScreen(pyte.HistoryScreen):
    """HistoryScreen subclass with alternate screen buffer support.

    Real terminals maintain two separate buffer objects and swap references
    on mode switches.  This avoids the deep-copy pitfall where
    ``StaticDefaultDict`` semantics (row defaults) are lost.

    Handled private modes:
      47   — legacy alt screen (swap only)
      1047 — alt screen (swap only)
      1048 — cursor save/restore only (no buffer swap)
      1049 — combined: cursor save + alt screen + clear
    """

    _alt_active: bool = False
    _saved_buffer: object | None = (
        None  # pyte's buffer (defaultdict of StaticDefaultDict)
    )
    _saved_cursor: tuple | None = None  # (x, y, attrs, hidden)

    def set_mode(self, *modes, **kwargs):
        private = kwargs.get("private", False)
        handled: set[int] = set()
        for mode in modes:
            if not private:
                continue
            if mode in (47, 1047):
                self._enter_alt_screen(save_cursor=False)
                handled.add(mode)
            elif mode == 1048:
                self._save_cursor()
                handled.add(mode)
            elif mode == 1049:
                self._enter_alt_screen(save_cursor=True)
                handled.add(mode)
        remaining = [m for m in modes if m not in handled]
        if remaining:
            super().set_mode(*remaining, **kwargs)

    def reset_mode(self, *modes, **kwargs):
        private = kwargs.get("private", False)
        handled: set[int] = set()
        for mode in modes:
            if not private:
                continue
            if mode in (47, 1047):
                self._exit_alt_screen(restore_cursor=False)
                handled.add(mode)
            elif mode == 1048:
                self._restore_cursor()
                handled.add(mode)
            elif mode == 1049:
                self._exit_alt_screen(restore_cursor=True)
                handled.add(mode)
        remaining = [m for m in modes if m not in handled]
        if remaining:
            super().reset_mode(*remaining, **kwargs)

    # ------------------------------------------------------------------

    def _save_cursor(self) -> None:
        cursor = self.cursor
        self._saved_cursor = (
            cursor.x,
            cursor.y,
            cursor.attrs,
            cursor.hidden,
        )

    def _restore_cursor(self) -> None:
        if self._saved_cursor is not None:
            x, y, attrs, hidden = self._saved_cursor
            self.cursor.x = x
            self.cursor.y = y
            self.cursor.attrs = attrs
            self.cursor.hidden = hidden
            self._saved_cursor = None

    def resize(self, lines=None, columns=None):
        old_columns = self.columns
        super().resize(lines=lines, columns=columns)
        if self._alt_active and self._saved_buffer is not None:
            if self.columns < old_columns:
                for line in self._saved_buffer.values():  # type: ignore[union-attr]
                    for x in range(self.columns, old_columns):
                        line.pop(x, None)

    def _enter_alt_screen(self, *, save_cursor: bool) -> None:
        if self._alt_active:
            return
        self._alt_active = True
        log.debug("Entering alt screen (save_cursor=%s, %dx%d)", save_cursor, self.lines, self.columns)

        if save_cursor:
            self._save_cursor()

        # O(1) reference swap — keeps full StaticDefaultDict semantics
        self._saved_buffer = self.buffer
        self.buffer = defaultdict(lambda: StaticDefaultDict(self.default_char))

        self.cursor.x = 0
        self.cursor.y = 0
        self.dirty.update(range(self.lines))

    def _exit_alt_screen(self, *, restore_cursor: bool) -> None:
        if not self._alt_active:
            return
        self._alt_active = False
        log.debug("Exiting alt screen (restore_cursor=%s, %dx%d)", restore_cursor, self.lines, self.columns)

        # O(1) reference restore
        self.buffer = self._saved_buffer  # type: ignore[assignment]
        self._saved_buffer = None

        if restore_cursor:
            self._restore_cursor()

        self.dirty.update(range(self.lines))


class _TerminalState:
    """Cached pyte terminal state for a single session."""

    __slots__ = ("session_id", "screen", "stream")

    def __init__(self, session_id: str, rows: int, cols: int) -> None:
        self.session_id = session_id
        self.screen = TAMEScreen(columns=cols, lines=rows, history=10000)
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
    _FALLBACK_MAX_CHARS: int = 500_000

    def __init__(self) -> None:
        super().__init__(id="session-viewer")
        if pyte is None:
            log.warning(
                "pyte unavailable; using degraded ANSI fallback renderer (%s)",
                _PYTE_IMPORT_ERROR,
            )
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
            self._fallback_text = self._append_fallback_text(self._fallback_text, text)
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
            self._fallback_text = self._append_fallback_text(
                "",
                output_buffer.get_all_text(),
            )
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
            self._fallback_text = self._append_fallback_text("", full_text)
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

    def show_snapshot(self, text: str) -> None:
        """Render a full-screen ANSI snapshot, replacing prior viewport state."""
        self._has_session = True
        self._scroll_offset = 0
        self._auto_scroll = True
        self._active_terminal = None
        self._fallback_text = text
        self.refresh()

    def feed_session(self, session_id: str, text: str) -> None:
        """Feed output into a background session's cached terminal."""
        if not text:
            return
        terminal = self._terminals.get(session_id)
        if terminal is not None:
            terminal.feed(text)

    def invalidate_session(self, session_id: str) -> None:
        """Drop cached terminal state for a background session.

        When the user later switches to this session, ``load_session()``
        will rebuild the terminal from the OutputBuffer automatically.
        """
        if session_id in self._terminals:
            terminal = self._terminals.pop(session_id)
            # Never invalidate the active terminal — only background ones
            if self._active_terminal is terminal:
                self._terminals[session_id] = terminal

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

        self.post_message(ViewerResized(rows, cols))
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
                run_chars: list[str] = []
                run_style: Style | None = None
                for x in range(cols):
                    char = row.get(x)
                    symbol = " " if char is None else (char.data or " ")
                    style = self._char_style(char)
                    if style == run_style:
                        run_chars.append(symbol)
                    else:
                        if run_chars:
                            output.append("".join(run_chars), style=run_style)
                        run_chars = [symbol]
                        run_style = style
                if run_chars:
                    output.append("".join(run_chars), style=run_style)
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
                run_chars = []
                run_style = None
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
                    if style == run_style:
                        run_chars.append(symbol)
                    else:
                        if run_chars:
                            output.append("".join(run_chars), style=run_style)
                        run_chars = [symbol]
                        run_style = style
                if run_chars:
                    output.append("".join(run_chars), style=run_style)
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

    @classmethod
    def _append_fallback_text(cls, existing: str, new_text: str) -> str:
        """Best-effort ANSI fallback state when pyte is unavailable.

        Rich's ANSI parser doesn't emulate display-clearing control sequences,
        so we trim content before the most recent full-screen clear.
        """
        merged = existing + new_text
        last_clear_end = -1
        for match in _FALLBACK_FULL_CLEAR_RE.finditer(merged):
            last_clear_end = match.end()
        if last_clear_end >= 0:
            merged = merged[last_clear_end:]
        if len(merged) > cls._FALLBACK_MAX_CHARS:
            merged = merged[-cls._FALLBACK_MAX_CHARS :]
        return merged
