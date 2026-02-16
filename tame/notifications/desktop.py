from __future__ import annotations

import logging
import shutil
import subprocess
from typing import ClassVar

from .models import NotificationEvent, Priority

log = logging.getLogger(__name__)


class DesktopNotifier:
    PRIORITY_URGENCY: ClassVar[dict[Priority, str]] = {
        Priority.CRITICAL: "critical",
        Priority.HIGH: "normal",
        Priority.MEDIUM: "low",
        Priority.LOW: "low",
    }

    def __init__(
        self,
        enabled: bool = True,
        urgency: str = "normal",
        icon_path: str = "",
        timeout_ms: int = 5000,
    ) -> None:
        self.enabled = enabled
        self.urgency = urgency
        self.icon_path = icon_path
        self.timeout_ms = timeout_ms

    def is_available(self) -> bool:
        return shutil.which("notify-send") is not None

    def notify(self, event: NotificationEvent) -> None:
        if not self.enabled:
            return

        if not self.is_available():
            log.warning("notify-send not found; desktop notifications unavailable")
            return

        urgency = self.PRIORITY_URGENCY.get(event.priority, self.urgency)

        cmd: list[str] = [
            "notify-send",
            "--urgency", urgency,
            "--expire-time", str(self.timeout_ms),
        ]

        if self.icon_path:
            cmd.extend(["--icon", self.icon_path])

        title = f"TAME: {event.session_name}"
        cmd.extend([title, event.message])

        try:
            subprocess.Popen(  # noqa: S603
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            log.warning("Failed to launch notify-send", exc_info=True)
