from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

from .models import NotificationEvent

log = logging.getLogger(__name__)


class WebhookNotifier:
    """Send notification events to a generic webhook URL as JSON POST."""

    def __init__(
        self,
        enabled: bool = False,
        url: str = "",
        headers: dict[str, str] | None = None,
        timeout: float = 5.0,
    ) -> None:
        self._enabled = enabled
        self._url = url
        self._headers = headers or {}
        self._timeout = timeout

    def notify(self, event: NotificationEvent) -> bool:
        """Send a notification event to the webhook.

        Returns True if the request was sent successfully.
        """
        if not self._enabled or not self._url:
            return False

        payload: dict[str, Any] = {
            "event_type": event.event_type.value,
            "session_id": event.session_id,
            "session_name": event.session_name,
            "message": event.message,
            "priority": event.priority.value,
            "matched_text": event.matched_text,
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
                **self._headers,
            }
            req = urllib.request.Request(
                self._url,
                data=data,
                headers=headers,
                method="POST",
            )
            urllib.request.urlopen(req, timeout=self._timeout)
            log.debug("Webhook sent to %s for %s", self._url, event.event_type.value)
            return True
        except Exception:
            log.warning("Failed to send webhook to %s", self._url, exc_info=True)
            return False
