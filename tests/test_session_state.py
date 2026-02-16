from __future__ import annotations

from tame.session.state import SessionState


def test_all_states_exist() -> None:
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


def test_state_values() -> None:
    assert SessionState.CREATED.value == "created"
    assert SessionState.STARTING.value == "starting"
    assert SessionState.ACTIVE.value == "active"
    assert SessionState.IDLE.value == "idle"
    assert SessionState.WAITING.value == "waiting"
    assert SessionState.PAUSED.value == "paused"
    assert SessionState.DONE.value == "done"
    assert SessionState.ERROR.value == "error"
