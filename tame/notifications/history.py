from __future__ import annotations

from collections import deque

from .models import NotificationEvent


class NotificationHistory:
    def __init__(self, max_size: int = 500) -> None:
        self._events: deque[NotificationEvent] = deque(maxlen=max_size)

    def add(self, event: NotificationEvent) -> None:
        self._events.append(event)

    def get_recent(self, n: int = 50) -> list[NotificationEvent]:
        items = list(self._events)
        return items[-n:]

    def get_all(self) -> list[NotificationEvent]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()

    def __len__(self) -> int:
        return len(self._events)
