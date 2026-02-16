from __future__ import annotations

from tame.session.state import (
    AttentionState,
    ProcessState,
    SessionState,
    compute_session_state,
)


def test_all_session_states_exist() -> None:
    expected = {
        "CREATED",
        "STARTING",
        "ACTIVE",
        "IDLE",
        "WAITING",
        "PAUSED",
        "DONE",
        "ERROR",
    }
    actual = {s.name for s in SessionState}
    assert actual == expected


def test_session_state_values() -> None:
    assert SessionState.CREATED.value == "created"
    assert SessionState.STARTING.value == "starting"
    assert SessionState.ACTIVE.value == "active"
    assert SessionState.IDLE.value == "idle"
    assert SessionState.WAITING.value == "waiting"
    assert SessionState.PAUSED.value == "paused"
    assert SessionState.DONE.value == "done"
    assert SessionState.ERROR.value == "error"


def test_all_process_states_exist() -> None:
    expected = {"STARTING", "RUNNING", "PAUSED", "EXITED"}
    actual = {s.name for s in ProcessState}
    assert actual == expected


def test_all_attention_states_exist() -> None:
    expected = {"NONE", "NEEDS_INPUT", "ERROR_SEEN", "IDLE"}
    actual = {s.name for s in AttentionState}
    assert actual == expected


# ------------------------------------------------------------------
# compute_session_state
# ------------------------------------------------------------------


def test_starting_gives_starting() -> None:
    assert compute_session_state(ProcessState.STARTING, AttentionState.NONE) is SessionState.STARTING


def test_paused_gives_paused() -> None:
    assert compute_session_state(ProcessState.PAUSED, AttentionState.NONE) is SessionState.PAUSED


def test_exited_clean_gives_done() -> None:
    assert compute_session_state(ProcessState.EXITED, AttentionState.NONE) is SessionState.DONE


def test_exited_with_error_gives_error() -> None:
    assert compute_session_state(ProcessState.EXITED, AttentionState.ERROR_SEEN) is SessionState.ERROR


def test_running_none_gives_active() -> None:
    assert compute_session_state(ProcessState.RUNNING, AttentionState.NONE) is SessionState.ACTIVE


def test_running_needs_input_gives_waiting() -> None:
    assert compute_session_state(ProcessState.RUNNING, AttentionState.NEEDS_INPUT) is SessionState.WAITING


def test_running_error_seen_gives_error() -> None:
    assert compute_session_state(ProcessState.RUNNING, AttentionState.ERROR_SEEN) is SessionState.ERROR


def test_running_idle_gives_idle() -> None:
    assert compute_session_state(ProcessState.RUNNING, AttentionState.IDLE) is SessionState.IDLE
