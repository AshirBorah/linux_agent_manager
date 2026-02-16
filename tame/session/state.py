from __future__ import annotations

from enum import Enum


class SessionState(Enum):
    CREATED = "created"
    STARTING = "starting"
    ACTIVE = "active"
    IDLE = "idle"
    WAITING = "waiting"      # Agent needs input
    PAUSED = "paused"        # SIGSTOP'd
    DONE = "done"            # Exited with code 0
    ERROR = "error"          # Exited with non-zero or error pattern
