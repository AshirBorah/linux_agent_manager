from __future__ import annotations

import pytest

from tame.session.state import (
    AttentionState,
    ProcessState,
    PRIORITY_ATTENTION_STATES,
    PRIORITY_PROCESS_STATES,
    VALID_ATTENTION_TRANSITIONS,
    VALID_PROCESS_TRANSITIONS,
    is_valid_attention_transition,
    is_valid_process_transition,
)


# ------------------------------------------------------------------
# ProcessState transitions
# ------------------------------------------------------------------


def test_starting_can_go_to_running() -> None:
    assert is_valid_process_transition(ProcessState.STARTING, ProcessState.RUNNING)


def test_starting_can_go_to_exited() -> None:
    assert is_valid_process_transition(ProcessState.STARTING, ProcessState.EXITED)


def test_starting_cannot_go_to_paused() -> None:
    assert not is_valid_process_transition(ProcessState.STARTING, ProcessState.PAUSED)


def test_running_can_go_to_paused() -> None:
    assert is_valid_process_transition(ProcessState.RUNNING, ProcessState.PAUSED)


def test_running_can_go_to_exited() -> None:
    assert is_valid_process_transition(ProcessState.RUNNING, ProcessState.EXITED)


def test_running_cannot_go_to_starting() -> None:
    assert not is_valid_process_transition(ProcessState.RUNNING, ProcessState.STARTING)


def test_paused_can_go_to_running() -> None:
    assert is_valid_process_transition(ProcessState.PAUSED, ProcessState.RUNNING)


def test_paused_can_go_to_exited() -> None:
    assert is_valid_process_transition(ProcessState.PAUSED, ProcessState.EXITED)


def test_exited_is_terminal() -> None:
    for target in ProcessState:
        assert not is_valid_process_transition(ProcessState.EXITED, target)


def test_self_transitions_invalid_for_process() -> None:
    for state in ProcessState:
        assert not is_valid_process_transition(state, state)


# ------------------------------------------------------------------
# AttentionState transitions
# ------------------------------------------------------------------


def test_none_can_go_to_needs_input() -> None:
    assert is_valid_attention_transition(AttentionState.NONE, AttentionState.NEEDS_INPUT)


def test_none_can_go_to_error_seen() -> None:
    assert is_valid_attention_transition(AttentionState.NONE, AttentionState.ERROR_SEEN)


def test_none_can_go_to_idle() -> None:
    assert is_valid_attention_transition(AttentionState.NONE, AttentionState.IDLE)


def test_needs_input_can_go_to_none() -> None:
    assert is_valid_attention_transition(AttentionState.NEEDS_INPUT, AttentionState.NONE)


def test_needs_input_can_go_to_error() -> None:
    assert is_valid_attention_transition(
        AttentionState.NEEDS_INPUT, AttentionState.ERROR_SEEN
    )


def test_needs_input_cannot_go_to_idle() -> None:
    assert not is_valid_attention_transition(
        AttentionState.NEEDS_INPUT, AttentionState.IDLE
    )


def test_error_seen_can_go_to_none() -> None:
    assert is_valid_attention_transition(AttentionState.ERROR_SEEN, AttentionState.NONE)


def test_idle_can_go_to_none() -> None:
    assert is_valid_attention_transition(AttentionState.IDLE, AttentionState.NONE)


def test_idle_can_go_to_needs_input() -> None:
    assert is_valid_attention_transition(
        AttentionState.IDLE, AttentionState.NEEDS_INPUT
    )


def test_idle_can_go_to_error_seen() -> None:
    assert is_valid_attention_transition(
        AttentionState.IDLE, AttentionState.ERROR_SEEN
    )


def test_self_transitions_invalid_for_attention() -> None:
    for state in AttentionState:
        assert not is_valid_attention_transition(state, state)


# ------------------------------------------------------------------
# Priority states
# ------------------------------------------------------------------


def test_error_seen_is_priority_attention() -> None:
    assert AttentionState.ERROR_SEEN in PRIORITY_ATTENTION_STATES


def test_needs_input_is_priority_attention() -> None:
    assert AttentionState.NEEDS_INPUT in PRIORITY_ATTENTION_STATES


def test_exited_is_priority_process() -> None:
    assert ProcessState.EXITED in PRIORITY_PROCESS_STATES


def test_none_is_not_priority_attention() -> None:
    assert AttentionState.NONE not in PRIORITY_ATTENTION_STATES


# ------------------------------------------------------------------
# All states have transition entries
# ------------------------------------------------------------------


def test_all_process_states_have_transition_entry() -> None:
    for state in ProcessState:
        assert state in VALID_PROCESS_TRANSITIONS


def test_all_attention_states_have_transition_entry() -> None:
    for state in AttentionState:
        assert state in VALID_ATTENTION_TRANSITIONS
