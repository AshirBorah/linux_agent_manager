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
        idx = self._available.index(self._current) if self._current in self._available else -1
        self._current = self._available[(idx + 1) % len(self._available)]
        return self._current

    def set_theme(self, name: str) -> bool:
        if name in self._available:
            self._current = name
            return True
        log.warning("Theme '%s' not available", name)
        return False
