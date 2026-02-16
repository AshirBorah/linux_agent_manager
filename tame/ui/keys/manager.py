from __future__ import annotations

import logging
from collections import defaultdict

log = logging.getLogger("tame.keys")

DEFAULT_KEYBINDINGS: dict[str, str] = {
    "new_session": "f2",
    "delete_session": "ctrl+d",
    "rename_session": "f9",
    "next_session": "f4",
    "prev_session": "f3",
    "resume_all": "f7",
    "pause_all": "f8",
    "stop_all": "ctrl+shift+q",
    "toggle_sidebar": "f6",
    "focus_search": "shift+tab",
    "focus_input": "ctrl+l",
    "save_state": "ctrl+s",
    "toggle_theme": "ctrl+t",
    "export_session_log": "ctrl+e",
    "quit": "f12",
    "session_1": "alt+1",
    "session_2": "alt+2",
    "session_3": "alt+3",
    "session_4": "alt+4",
    "session_5": "alt+5",
    "session_6": "alt+6",
    "session_7": "alt+7",
    "session_8": "alt+8",
    "session_9": "alt+9",
}


class KeybindManager:
    def __init__(self, user_bindings: dict[str, str] | None = None) -> None:
        self._bindings: dict[str, str] = dict(DEFAULT_KEYBINDINGS)
        self._conflicts: list[str] = []

        if user_bindings:
            for action, key in user_bindings.items():
                if action in self._bindings:
                    self._bindings[action] = key

        self._detect_conflicts()

    def _detect_conflicts(self) -> None:
        key_to_actions: dict[str, list[str]] = defaultdict(list)
        for action, key in self._bindings.items():
            key_to_actions[key].append(action)

        self._conflicts = []
        for key, actions in key_to_actions.items():
            if len(actions) > 1:
                msg = f"Key '{key}' bound to multiple actions: {', '.join(actions)}"
                self._conflicts.append(msg)
                log.warning(msg)

    @property
    def conflicts(self) -> list[str]:
        return list(self._conflicts)

    def get_key(self, action: str) -> str | None:
        return self._bindings.get(action)

    def get_action(self, key: str) -> str | None:
        for action, bound_key in self._bindings.items():
            if bound_key == key:
                return action
        return None

    def get_all(self) -> dict[str, str]:
        return dict(self._bindings)
