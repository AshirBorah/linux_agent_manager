from __future__ import annotations

import logging
from enum import Enum

log = logging.getLogger(__name__)


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


# Valid state transitions for ProcessState
VALID_PROCESS_TRANSITIONS: dict[ProcessState, frozenset[ProcessState]] = {
    ProcessState.STARTING: frozenset({ProcessState.RUNNING, ProcessState.EXITED}),
    ProcessState.RUNNING: frozenset(
        {ProcessState.PAUSED, ProcessState.EXITED}
    ),
    ProcessState.PAUSED: frozenset(
        {ProcessState.RUNNING, ProcessState.EXITED}
    ),
    ProcessState.EXITED: frozenset(),  # terminal state
}

# Valid state transitions for AttentionState
VALID_ATTENTION_TRANSITIONS: dict[AttentionState, frozenset[AttentionState]] = {
    AttentionState.NONE: frozenset(
        {AttentionState.NEEDS_INPUT, AttentionState.ERROR_SEEN, AttentionState.IDLE}
    ),
    AttentionState.NEEDS_INPUT: frozenset(
        {AttentionState.NONE, AttentionState.ERROR_SEEN}
    ),
    AttentionState.ERROR_SEEN: frozenset(
        {AttentionState.NONE, AttentionState.NEEDS_INPUT}
    ),
    AttentionState.IDLE: frozenset(
        {AttentionState.NONE, AttentionState.NEEDS_INPUT, AttentionState.ERROR_SEEN}
    ),
}

# States that bypass debounce (critical transitions)
PRIORITY_ATTENTION_STATES: frozenset[AttentionState] = frozenset(
    {AttentionState.ERROR_SEEN, AttentionState.NEEDS_INPUT}
)

PRIORITY_PROCESS_STATES: frozenset[ProcessState] = frozenset(
    {ProcessState.EXITED}
)


def is_valid_process_transition(
    current: ProcessState, target: ProcessState
) -> bool:
    """Check whether a ProcessState transition is allowed."""
    return target in VALID_PROCESS_TRANSITIONS.get(current, frozenset())


def is_valid_attention_transition(
    current: AttentionState, target: AttentionState
) -> bool:
    """Check whether an AttentionState transition is allowed."""
    return target in VALID_ATTENTION_TRANSITIONS.get(current, frozenset())


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
