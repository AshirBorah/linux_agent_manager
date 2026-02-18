from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("tame.themes")

BUILTIN_DIR = Path(__file__).parent / "builtin"

BUILTIN_THEMES = [
    "dark",
    "light",
    "dracula",
    "nord",
    "monokai",
    "gruvbox",
    "solarized_dark",
    "solarized_light",
]

# Colors for widgets that actually exist in the app.
# Each entry: (background, foreground) per widget selector.
THEME_COLORS: dict[str, dict[str, tuple[str, str]]] = {
    "dark": {
        "screen": ("#1e1e1e", "#d4d4d4"),
        "header": ("#007acc", "#ffffff"),
        "sidebar": ("#252526", "#d4d4d4"),
        "viewer": ("#1e1e1e", "#d4d4d4"),
        "status": ("#007acc", "#ffffff"),
    },
    "light": {
        "screen": ("#ffffff", "#333333"),
        "header": ("#007acc", "#ffffff"),
        "sidebar": ("#f3f3f3", "#333333"),
        "viewer": ("#ffffff", "#333333"),
        "status": ("#007acc", "#ffffff"),
    },
    "dracula": {
        "screen": ("#282a36", "#f8f8f2"),
        "header": ("#6272a4", "#f8f8f2"),
        "sidebar": ("#21222c", "#f8f8f2"),
        "viewer": ("#282a36", "#f8f8f2"),
        "status": ("#bd93f9", "#282a36"),
    },
    "nord": {
        "screen": ("#2e3440", "#d8dee9"),
        "header": ("#5e81ac", "#eceff4"),
        "sidebar": ("#3b4252", "#d8dee9"),
        "viewer": ("#2e3440", "#d8dee9"),
        "status": ("#5e81ac", "#eceff4"),
    },
    "monokai": {
        "screen": ("#272822", "#f8f8f2"),
        "header": ("#75715e", "#f8f8f2"),
        "sidebar": ("#1e1f1c", "#f8f8f2"),
        "viewer": ("#272822", "#f8f8f2"),
        "status": ("#66d9ef", "#272822"),
    },
    "gruvbox": {
        "screen": ("#282828", "#ebdbb2"),
        "header": ("#458588", "#ebdbb2"),
        "sidebar": ("#1d2021", "#ebdbb2"),
        "viewer": ("#282828", "#ebdbb2"),
        "status": ("#458588", "#ebdbb2"),
    },
    "solarized_dark": {
        "screen": ("#002b36", "#839496"),
        "header": ("#268bd2", "#fdf6e3"),
        "sidebar": ("#073642", "#839496"),
        "viewer": ("#002b36", "#839496"),
        "status": ("#268bd2", "#fdf6e3"),
    },
    "solarized_light": {
        "screen": ("#fdf6e3", "#657b83"),
        "header": ("#268bd2", "#fdf6e3"),
        "sidebar": ("#eee8d5", "#657b83"),
        "viewer": ("#fdf6e3", "#657b83"),
        "status": ("#268bd2", "#fdf6e3"),
    },
}


class ThemeManager:
    def __init__(self, current: str = "dark", custom_css_path: str = "") -> None:
        self._current = current if current in BUILTIN_THEMES else "dark"
        self._custom_css_path = custom_css_path
        self._available = self._discover_themes()

    def _discover_themes(self) -> list[str]:
        themes = []
        for name in BUILTIN_THEMES:
            path = BUILTIN_DIR / f"{name}.tcss"
            if path.exists():
                themes.append(name)
        return themes

    @property
    def current(self) -> str:
        return self._current

    @property
    def available(self) -> list[str]:
        return list(self._available)

    def get_css_path(self, theme_name: str | None = None) -> Path | None:
        name = theme_name or self._current
        if self._custom_css_path and name == self._current:
            custom = Path(self._custom_css_path).expanduser()
            if custom.exists():
                return custom
        path = BUILTIN_DIR / f"{name}.tcss"
        if path.exists():
            return path
        log.warning("Theme '%s' not found, falling back to dark", name)
        return BUILTIN_DIR / "dark.tcss"

    def get_css(self, theme_name: str | None = None) -> str:
        path = self.get_css_path(theme_name)
        if path and path.exists():
            return path.read_text()
        return ""

    def cycle(self) -> str:
        if not self._available:
            return self._current
        idx = (
            self._available.index(self._current)
            if self._current in self._available
            else -1
        )
        self._current = self._available[(idx + 1) % len(self._available)]
        return self._current

    def get_colors(self, theme_name: str | None = None) -> dict[str, tuple[str, str]]:
        """Return (background, foreground) pairs for the given theme."""
        name = theme_name or self._current
        return THEME_COLORS.get(name, THEME_COLORS["dark"])

    def set_theme(self, name: str) -> bool:
        if name in self._available:
            self._current = name
            return True
        log.warning("Theme '%s' not available", name)
        return False
