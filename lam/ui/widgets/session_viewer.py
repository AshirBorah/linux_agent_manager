from __future__ import annotations

from functools import lru_cache

from rich.style import Style
from rich.text import Text
from textual import events
from textual.widget import Widget

from lam.session.output_buffer import OutputBuffer

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

    def __init__(self) -> None:
        super().__init__(id="session-viewer")
        self._fallback_text: str = ""
        self._rows: int = 24
        self._cols: int = 80
        self._screen = None
        self._stream = None
        self._has_session: bool = False
        if pyte is not None:
            self._reset_terminal(rows=self._rows, cols=self._cols)

    def append_output(self, text: str) -> None:
        """Feed new PTY output into terminal state and refresh display."""
        if not text:
            return

        if self._stream is None:
            self._fallback_text += text
            self.refresh()
            return

        self._stream.feed(text)
        self.refresh()

    def load_buffer(self, output_buffer: OutputBuffer) -> None:
        """Reset terminal state and replay buffer contents."""
        self._has_session = True
        full_text = output_buffer.get_all_text()
        if self._stream is None:
            self._fallback_text = full_text
            self.refresh()
            return

        rows = max(1, self.size.height or self._rows)
        cols = max(1, self.size.width or self._cols)
        self._reset_terminal(rows=rows, cols=cols)
        if full_text:
            self._stream.feed(full_text)
        self.refresh()

    def on_resize(self, event: events.Resize) -> None:
        rows = max(1, event.size.height)
        cols = max(1, event.size.width)
        if self._stream is None or self._screen is None:
            self._rows = rows
            self._cols = cols
            return

        self._screen.resize(lines=rows, columns=cols)
        self._rows = rows
        self._cols = cols
        self.refresh()

    def render(self) -> Text:
        if not self._has_session:
            return Text.from_markup(
                "\n\n\n"
                "  [bold]No active session[/bold]\n\n"
                "  Press [bold]F2[/bold] or click [bold]+ New Session[/bold] to get started.\n"
            )
        if self._stream is None or self._screen is None:
            return Text.from_ansi(self._fallback_text)
        return self._render_terminal_text()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _reset_terminal(self, rows: int, cols: int) -> None:
        if pyte is None:  # pragma: no cover
            return
        self._rows = rows
        self._cols = cols
        self._screen = pyte.Screen(columns=cols, lines=rows)
        self._stream = pyte.Stream(self._screen)

    def _render_terminal_text(self) -> Text:
        assert self._screen is not None
        rows = max(1, self._rows)
        cols = max(1, self._cols)
        cursor = self._screen.cursor
        cursor_x = getattr(cursor, "x", -1)
        cursor_y = getattr(cursor, "y", -1)
        cursor_hidden = bool(getattr(cursor, "hidden", False))
        has_focus = self.has_focus

        output = Text()
        buffer = self._screen.buffer

        for y in range(rows):
            row = buffer.get(y, {})
            for x in range(cols):
                char = row.get(x)
                symbol = " " if char is None else (char.data or " ")
                style = self._char_style(char)
                if has_focus and not cursor_hidden and x == cursor_x and y == cursor_y:
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
        fg_name = _FG_COLOR_MAP.get(fg, fg)
        bg_name = _BG_COLOR_MAP.get(bg, bg)
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
