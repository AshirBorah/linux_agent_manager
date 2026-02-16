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


def test_custom_patterns_merge_with_defaults() -> None:
    manager = SessionManager(patterns={"error": [r"(?i)boom"]})
    assert "prompt" in manager._patterns
    assert r"\[y/n\]" in manager._patterns["prompt"]


# ------------------------------------------------------------------
# scan_pane_content
# ------------------------------------------------------------------


def test_scan_pane_content_detects_prompt() -> None:
    manager, session, transitions = _make_manager_with_session()

    pane_text = (
        "Some output line\n"
        "Another line of output\n"
        "Do you want to proceed? [y/n]\n"
    )
    manager.scan_pane_content(session.id, pane_text)
    assert session.status is SessionState.WAITING
    assert (SessionState.ACTIVE, SessionState.WAITING) in transitions


def test_scan_pane_content_detects_error() -> None:
    manager, session, transitions = _make_manager_with_session()

    pane_text = (
        "Starting task...\n"
        "Traceback (most recent call last)\n"
        "  File 'foo.py', line 1\n"
    )
    manager.scan_pane_content(session.id, pane_text)
    assert session.status is SessionState.ERROR
    assert (SessionState.ACTIVE, SessionState.ERROR) in transitions


def test_scan_pane_content_detects_completion() -> None:
    manager, session, transitions = _make_manager_with_session()

    pane_text = "Step 1/3\nStep 2/3\nTask completed\n"
    manager.scan_pane_content(session.id, pane_text)
    assert session.status is SessionState.DONE
    assert (SessionState.ACTIVE, SessionState.DONE) in transitions


def test_scan_pane_content_last_match_wins() -> None:
    manager, session, transitions = _make_manager_with_session()

    pane_text = (
        "Error: something went wrong\n"
        "Recovered\n"
        "Continue? [y/n]\n"
    )
    manager.scan_pane_content(session.id, pane_text)
    assert session.status is SessionState.WAITING


def test_scan_pane_content_no_match_keeps_status() -> None:
    manager, session, transitions = _make_manager_with_session()

    pane_text = "just some normal output\nnothing special here\n"
    manager.scan_pane_content(session.id, pane_text)
    assert session.status is SessionState.ACTIVE
    assert transitions == []


def test_scan_pane_content_prompt_without_trailing_newline() -> None:
    manager, session, transitions = _make_manager_with_session()

    pane_text = "Some output\nProceed? [y/n]"
    manager.scan_pane_content(session.id, pane_text)
    assert session.status is SessionState.WAITING
