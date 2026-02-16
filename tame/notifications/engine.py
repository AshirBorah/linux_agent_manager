from __future__ import annotations

import logging
from datetime import datetime, time
from typing import Any, Callable

from .audio import AudioNotifier
from .desktop import DesktopNotifier
from .history import NotificationHistory
from .models import EVENT_PRIORITY, EventType, NotificationEvent, Priority

# Seconds before the same (session, event_type) can fire again.
_DEFAULT_COOLDOWN: dict[EventType, float] = {
    EventType.ERROR: 60.0,
    EventType.SESSION_IDLE: 120.0,
}

log = logging.getLogger(__name__)

DEFAULT_ROUTING: dict[str, dict[str, bool]] = {
    "input_needed": {
        "desktop": True,
        "audio": True,
        "toast": True,
        "sidebar_flash": True,
    },
    "error": {
        "desktop": True,
        "audio": True,
        "toast": True,
        "sidebar_flash": True,
    },
    "completed": {
        "desktop": True,
        "audio": True,
        "toast": True,
        "sidebar_flash": False,
    },
    "session_idle": {
        "desktop": False,
        "audio": False,
        "toast": True,
        "sidebar_flash": False,
    },
}


class NotificationEngine:
    def __init__(self, config: dict[str, Any]) -> None:
        desktop_cfg = config.get("desktop", {})
        self._desktop = DesktopNotifier(
            enabled=desktop_cfg.get("enabled", True),
            urgency=desktop_cfg.get("urgency", "normal"),
            icon_path=desktop_cfg.get("icon_path", ""),
            timeout_ms=desktop_cfg.get("timeout_ms", 5000),
        )

        audio_cfg = config.get("audio", {})
        self._audio = AudioNotifier(
            enabled=audio_cfg.get("enabled", True),
            volume=audio_cfg.get("volume", 0.7),
            backend_preference=audio_cfg.get("backend_preference"),
            sounds=audio_cfg.get("sounds"),
        )

        history_cfg = config.get("history", {})
        self._history = NotificationHistory(
            max_size=history_cfg.get("max_size", 500),
        )

        self._routing: dict[str, dict[str, bool]] = config.get(
            "routing", DEFAULT_ROUTING
        )

        dnd_cfg = config.get("dnd", {})
        self._dnd_enabled: bool = dnd_cfg.get("enabled", False)
        self._dnd_start: time | None = _parse_time(dnd_cfg.get("start"))
        self._dnd_end: time | None = _parse_time(dnd_cfg.get("end"))

        self.on_toast: Callable[[NotificationEvent], Any] | None = None
        self.on_sidebar_flash: Callable[[NotificationEvent], Any] | None = None

        # Per-(session, event_type) cooldown to avoid notification spam.
        self._last_fired: dict[tuple[str, EventType], float] = {}

    def dispatch(
        self,
        event_type: EventType,
        session_id: str,
        session_name: str,
        message: str,
        matched_text: str = "",
    ) -> NotificationEvent:
        priority = EVENT_PRIORITY.get(event_type, Priority.MEDIUM)
        event = NotificationEvent(
            event_type=event_type,
            session_id=session_id,
            session_name=session_name,
            message=message,
            priority=priority,
            matched_text=matched_text,
        )

        self._history.add(event)

        if self._is_dnd():
            log.debug("DND active — suppressing notification channels")
            return event

        # Per-(session, event_type) cooldown to suppress repeated noise.
        cooldown = _DEFAULT_COOLDOWN.get(event_type, 0.0)
        if cooldown > 0:
            key = (session_id, event_type)
            now = datetime.now().timestamp()
            last = self._last_fired.get(key, 0.0)
            if now - last < cooldown:
                log.debug(
                    "Suppressed %s for session %s (cooldown %.0fs)",
                    event_type.value, session_id, cooldown,
                )
                return event
            self._last_fired[key] = now

        routes = self._routing.get(event_type.value, {})

        if routes.get("desktop", False):
            self._desktop.notify(event)

        if routes.get("audio", False):
            self._audio.notify(event)

        if routes.get("toast", False) and self.on_toast is not None:
            self.on_toast(event)

        if routes.get("sidebar_flash", False) and self.on_sidebar_flash is not None:
            self.on_sidebar_flash(event)

        return event

    def _is_dnd(self) -> bool:
        if not self._dnd_enabled:
            return False

        if self._dnd_start is None or self._dnd_end is None:
            return self._dnd_enabled

        now = datetime.now().time()

        # Handle overnight ranges (e.g., 22:00 -> 07:00)
        if self._dnd_start <= self._dnd_end:
            return self._dnd_start <= now <= self._dnd_end
        return now >= self._dnd_start or now <= self._dnd_end

    def set_dnd(self, enabled: bool) -> None:
        self._dnd_enabled = enabled

    def get_history(self) -> NotificationHistory:
        return self._history


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    try:
        parts = value.split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        log.warning("Invalid time format %r, expected HH:MM", value)
        return None
