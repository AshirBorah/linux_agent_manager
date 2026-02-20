from __future__ import annotations

import random

from rich.segment import Segment
from rich.style import Style
from textual.strip import Strip
from textual.timer import Timer
from textual.widget import Widget


class CherryBlossomPetals(Widget):
    """Animated falling cherry blossom petals overlay.

    Only visible when the cherry_blossom theme is active.
    Renders sparse ASCII petals drifting downward across the screen.
    """

    DEFAULT_CSS = """
    CherryBlossomPetals {
        layer: overlay;
        width: 1fr;
        height: 1fr;
        display: none;
    }
    """

    PETAL_CHARS = ("*", ".", "~", "*", ".", "°")
    PETAL_COLORS = ("#d4678e", "#e891a8", "#ffb6d9", "#ffc9dd", "#f0a0b8")

    can_focus = False

    def __init__(self) -> None:
        super().__init__(id="cherry-blossom-petals")
        # Each petal: [row_float, col_int, char, color_hex, speed_float]
        self._petals: list[list] = []
        self._animation_timer: Timer | None = None

    def on_mount(self) -> None:
        self._animation_timer = self.set_interval(0.15, self._tick)

    def _tick(self) -> None:
        if not self.display:
            return

        height = self.size.height
        width = self.size.width
        if height <= 0 or width <= 0:
            return

        # Move existing petals downward with slight horizontal drift.
        surviving: list[list] = []
        for petal in self._petals:
            row, col, char, color, speed = petal
            new_row = row + speed
            new_col = col + random.choice([-1, 0, 0, 0, 1])
            if new_row < height and 0 <= new_col < width:
                surviving.append([new_row, new_col, char, color, speed])

        # Spawn a new petal occasionally (keep density low).
        if random.random() < 0.35:
            col = random.randint(0, max(0, width - 1))
            char = random.choice(self.PETAL_CHARS)
            color = random.choice(self.PETAL_COLORS)
            speed = random.choice([0.5, 1.0, 1.0, 1.5])
            surviving.append([0.0, col, char, color, speed])

        self._petals = surviving
        self.refresh()

    def render_line(self, y: int) -> Strip:
        """Render a single line of the petal overlay."""
        width = self.size.width
        if width <= 0:
            return Strip.blank(width)

        # Collect petals on this row.
        row_petals: dict[int, tuple[str, str]] = {}
        for petal in self._petals:
            row, col, char, color, _speed = petal
            if int(row) == y and 0 <= int(col) < width:
                row_petals[int(col)] = (char, color)

        if not row_petals:
            return Strip.blank(width)

        # Build segments: spaces for empty cells, styled chars for petals.
        segments: list[Segment] = []
        blank = Style()
        i = 0
        while i < width:
            if i in row_petals:
                char, color = row_petals[i]
                segments.append(Segment(char, Style(color=color, bold=True)))
                i += 1
            else:
                # Accumulate consecutive blank spaces.
                start = i
                while i < width and i not in row_petals:
                    i += 1
                segments.append(Segment(" " * (i - start), blank))

        return Strip(segments, width)
