from __future__ import annotations

from datetime import datetime, timezone

from lam.session.manager import SessionManager
from lam.session.output_buffer import OutputBuffer
from lam.session.pattern_matcher import PatternMatcher
from lam.session.session import Session
from lam.session.state import SessionState


def _make_manager_with_session() -> tuple[SessionManager, Session, list[tuple[SessionState, SessionState]]]:
    transitions: list[tuple[SessionState, SessionState]] = []

    def on_status(_sid: str, old: SessionState, new: SessionState) -> None:
        transitions.append((old, new))

    manager = SessionManager(on_status_change=on_status)
    now = datetime.now(timezone.utc)
    session = Session(
        id="s1",
        name="s1",
        working_dir=".",
        status=SessionState.ACTIVE,
        created_at=now,
        last_activity=now,
        output_buffer=OutputBuffer(),
        pattern_matcher=PatternMatcher(manager._patterns),
        pid=None,
        pty_process=None,
    )
    manager._sessions[session.id] = session
    return manager, session, transitions


def test_prompt_detected_when_split_across_chunks() -> None:
    manager, session, transitions = _make_manager_with_session()

    manager._on_session_output(session.id, b"Do you want to pro")
    assert session.status is SessionState.ACTIVE

    manager._on_session_output(session.id, b"ceed?\n1. Yes\n")
    assert session.status is SessionState.WAITING
    assert (SessionState.ACTIVE, SessionState.WAITING) in transitions


def test_prompt_detected_without_trailing_newline() -> None:
    manager, session, transitions = _make_manager_with_session()

    manager._on_session_output(session.id, b"Proceed? [y/n]")
    assert session.status is SessionState.WAITING
    assert (SessionState.ACTIVE, SessionState.WAITING) in transitions
