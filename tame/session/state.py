from __future__ import annotations

from enum import Enum


class ProcessState(Enum):
    """Lifecycle state of the underlying process."""

    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    EXITED = "exited"


class AttentionState(Enum):
    """Whether the session needs user attention."""

    NONE = "none"
    NEEDS_INPUT = "needs_input"
    ERROR_SEEN = "error_seen"
    IDLE = "idle"


class SessionState(Enum):
    """Combined display state derived from ProcessState + AttentionState."""

    CREATED = "created"
    STARTING = "starting"
    ACTIVE = "active"
    IDLE = "idle"
    WAITING = "waiting"  # Agent needs input
    PAUSED = "paused"  # SIGSTOP'd
    DONE = "done"  # Exited with code 0
    ERROR = "error"  # Exited with non-zero or error pattern


def compute_session_state(
    process: ProcessState, attention: AttentionState
) -> SessionState:
    """Derive the display SessionState from ProcessState + AttentionState."""
    if process is ProcessState.STARTING:
        return SessionState.STARTING
    if process is ProcessState.PAUSED:
        return SessionState.PAUSED
    if process is ProcessState.EXITED:
        if attention is AttentionState.ERROR_SEEN:
            return SessionState.ERROR
        return SessionState.DONE
    # RUNNING
    if attention is AttentionState.NEEDS_INPUT:
        return SessionState.WAITING
    if attention is AttentionState.ERROR_SEEN:
        return SessionState.ERROR
    if attention is AttentionState.IDLE:
        return SessionState.IDLE
    return SessionState.ACTIVE
