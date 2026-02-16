from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class EventType(Enum):
    INPUT_NEEDED = "input_needed"
    ERROR = "error"
    COMPLETED = "completed"
    SESSION_IDLE = "session_idle"


class Priority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


EVENT_PRIORITY: dict[EventType, Priority] = {
    EventType.INPUT_NEEDED: Priority.HIGH,
    EventType.ERROR: Priority.CRITICAL,
    EventType.COMPLETED: Priority.MEDIUM,
    EventType.SESSION_IDLE: Priority.LOW,
}


@dataclass
class NotificationEvent:
    event_type: EventType
    session_id: str
    session_name: str
    message: str
    priority: Priority
    timestamp: datetime = field(default_factory=datetime.now)
    matched_text: str = ""
