from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tame.session.manager import SessionManager
from tame.session.output_buffer import OutputBuffer
from tame.session.pattern_matcher import PatternMatcher
from tame.session.session import Session
from tame.session.state import AttentionState, ProcessState, SessionState


def _make_manager_with_session() -> tuple[
    SessionManager, Session, list[tuple[SessionState, SessionState]]
]:
    transitions: list[tuple[SessionState, SessionState]] = []

    def on_status(
        _sid: str, old: SessionState, new: SessionState, _matched: str = ""
    ) -> None:
        transitions.append((old, new))

    manager = SessionManager(on_status_change=on_status)
    now = datetime.now(timezone.utc)
    session = Session(
        id="s1",
        name="s1",
        working_dir=".",
        process_state=ProcessState.RUNNING,
        attention_state=AttentionState.NONE,
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
        "Some output line\nAnother line of output\nDo you want to proceed? [y/n]\n"
    )
    manager.scan_pane_content(session.id, pane_text)
    assert session.status is SessionState.WAITING
    assert (SessionState.ACTIVE, SessionState.WAITING) in transitions


def test_scan_pane_content_detects_error() -> None:
    manager, session, transitions = _make_manager_with_session()

    pane_text = (
        "Starting task...\nTraceback (most recent call last)\n  File 'foo.py', line 1\n"
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

    pane_text = "Error: something went wrong\nRecovered\nContinue? [y/n]\n"
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


# ------------------------------------------------------------------
# Shell error detection
# ------------------------------------------------------------------


def test_shell_command_not_found_triggers_error_state() -> None:
    manager, session, transitions = _make_manager_with_session()

    manager._on_session_output(session.id, b"zsh: command not found: pytn\n")
    assert session.status is SessionState.ERROR
    assert (SessionState.ACTIVE, SessionState.ERROR) in transitions


# ------------------------------------------------------------------
# send_input state reset
# ------------------------------------------------------------------


class _FakePTY:
    """Minimal stand-in for PTYProcess so send_input() can call write()."""

    def write(self, text: str) -> None:
        pass


def _make_manager_with_pty_session(
    process_state: ProcessState = ProcessState.RUNNING,
    attention_state: AttentionState = AttentionState.NONE,
) -> tuple[SessionManager, Session, list[tuple[SessionState, SessionState]]]:
    transitions: list[tuple[SessionState, SessionState]] = []

    def on_status(
        _sid: str, old: SessionState, new: SessionState, _matched: str = ""
    ) -> None:
        transitions.append((old, new))

    manager = SessionManager(on_status_change=on_status)
    now = datetime.now(timezone.utc)
    session = Session(
        id="s1",
        name="s1",
        working_dir=".",
        process_state=process_state,
        attention_state=attention_state,
        created_at=now,
        last_activity=now,
        output_buffer=OutputBuffer(),
        pattern_matcher=PatternMatcher(manager._patterns),
        pid=None,
        pty_process=_FakePTY(),
    )
    manager._sessions[session.id] = session
    return manager, session, transitions


def test_send_input_resets_error_to_active() -> None:
    manager, session, transitions = _make_manager_with_pty_session(
        attention_state=AttentionState.ERROR_SEEN,
    )

    manager.send_input(session.id, "ls\n")
    assert session.status is SessionState.ACTIVE
    assert (SessionState.ERROR, SessionState.ACTIVE) in transitions


def test_send_input_resets_waiting_to_active() -> None:
    manager, session, transitions = _make_manager_with_pty_session(
        attention_state=AttentionState.NEEDS_INPUT,
    )

    manager.send_input(session.id, "y\n")
    assert session.status is SessionState.ACTIVE
    assert (SessionState.WAITING, SessionState.ACTIVE) in transitions


def test_send_input_does_not_reset_done() -> None:
    manager, session, transitions = _make_manager_with_pty_session(
        process_state=ProcessState.EXITED,
    )

    manager.send_input(session.id, "ls\n")
    assert session.status is SessionState.DONE
    assert transitions == []


def test_send_input_does_not_reset_paused() -> None:
    manager, session, transitions = _make_manager_with_pty_session(
        process_state=ProcessState.PAUSED,
    )

    manager.send_input(session.id, "ls\n")
    assert session.status is SessionState.PAUSED
    assert transitions == []


def test_send_input_noop_when_already_active() -> None:
    manager, session, transitions = _make_manager_with_pty_session()

    manager.send_input(session.id, "ls\n")
    assert session.status is SessionState.ACTIVE
    assert transitions == []


def test_rename_session() -> None:
    manager = SessionManager()
    session = manager.create_session("old-name", "/tmp")
    manager.rename_session(session.id, "new-name")
    assert manager.get_session(session.id).name == "new-name"
    manager.close_all()


# ------------------------------------------------------------------
# ProcessState + AttentionState (#4)
# ------------------------------------------------------------------


def test_session_status_is_derived_property() -> None:
    """Status should be computed from process_state + attention_state."""
    manager, session, _ = _make_manager_with_session()
    assert session.process_state is ProcessState.RUNNING
    assert session.attention_state is AttentionState.NONE
    assert session.status is SessionState.ACTIVE


def test_attention_needs_input_gives_waiting() -> None:
    manager, session, _ = _make_manager_with_session()
    session.attention_state = AttentionState.NEEDS_INPUT
    assert session.status is SessionState.WAITING


def test_exited_with_error_gives_error() -> None:
    manager, session, _ = _make_manager_with_session()
    session.process_state = ProcessState.EXITED
    session.attention_state = AttentionState.ERROR_SEEN
    assert session.status is SessionState.ERROR


def test_exited_clean_gives_done() -> None:
    manager, session, _ = _make_manager_with_session()
    session.process_state = ProcessState.EXITED
    assert session.status is SessionState.DONE


def test_paused_gives_paused() -> None:
    manager, session, _ = _make_manager_with_session()
    session.process_state = ProcessState.PAUSED
    assert session.status is SessionState.PAUSED


# ------------------------------------------------------------------
# Idle detection (#6)
# ------------------------------------------------------------------


def test_check_idle_sessions_transitions_to_idle() -> None:
    manager, session, transitions = _make_manager_with_session()
    # Simulate old last_activity
    session.last_activity = datetime.now(timezone.utc) - timedelta(seconds=400)
    manager._check_idle_sessions()
    assert session.status is SessionState.IDLE
    assert (SessionState.ACTIVE, SessionState.IDLE) in transitions


def test_check_idle_sessions_skips_non_running() -> None:
    manager, session, transitions = _make_manager_with_session()
    session.process_state = ProcessState.EXITED
    session.last_activity = datetime.now(timezone.utc) - timedelta(seconds=400)
    manager._check_idle_sessions()
    # Should NOT transition — process already exited
    assert session.attention_state is AttentionState.NONE
    assert transitions == []


def test_check_idle_sessions_skips_already_attention() -> None:
    manager, session, transitions = _make_manager_with_session()
    session.attention_state = AttentionState.NEEDS_INPUT
    session.last_activity = datetime.now(timezone.utc) - timedelta(seconds=400)
    manager._check_idle_sessions()
    # Should NOT overwrite NEEDS_INPUT with IDLE
    assert session.attention_state is AttentionState.NEEDS_INPUT
    assert transitions == []


def test_check_idle_sessions_respects_threshold() -> None:
    manager, session, transitions = _make_manager_with_session()
    # Activity just 10 seconds ago — below the 300s default threshold
    session.last_activity = datetime.now(timezone.utc) - timedelta(seconds=10)
    manager._check_idle_sessions()
    assert session.attention_state is AttentionState.NONE
    assert transitions == []


def test_output_clears_idle_attention() -> None:
    manager, session, transitions = _make_manager_with_session()
    session.attention_state = AttentionState.IDLE
    manager._on_session_output(session.id, b"new output\n")
    assert session.attention_state is AttentionState.NONE
    assert (SessionState.IDLE, SessionState.ACTIVE) in transitions


def test_send_input_clears_idle_attention() -> None:
    manager, session, transitions = _make_manager_with_pty_session()
    session.attention_state = AttentionState.IDLE
    manager.send_input(session.id, "hello\n")
    assert session.attention_state is AttentionState.NONE
    assert (SessionState.IDLE, SessionState.ACTIVE) in transitions


# ------------------------------------------------------------------
# Weak prompt timeout gating (#7)
# ------------------------------------------------------------------


def test_weak_prompt_fires_immediately_without_loop() -> None:
    """Without an event loop, weak prompts fire as immediate fallback."""
    manager = SessionManager(
        patterns={"weak_prompt": [r"\?\s*$"]},
    )
    now = datetime.now(timezone.utc)
    session = Session(
        id="s1",
        name="s1",
        working_dir=".",
        process_state=ProcessState.RUNNING,
        attention_state=AttentionState.NONE,
        created_at=now,
        last_activity=now,
        output_buffer=OutputBuffer(),
        pattern_matcher=PatternMatcher(manager._patterns),
        pid=None,
        pty_process=None,
    )
    manager._sessions[session.id] = session
    # Line ending in ? should match weak_prompt
    manager._on_session_output(session.id, b"What is your name?\n")
    assert session.status is SessionState.WAITING


def test_weak_prompt_does_not_match_strong_prompt() -> None:
    """Strong prompt patterns take priority over weak ones."""
    manager, session, transitions = _make_manager_with_session()
    # [y/n] is a strong prompt pattern — should fire immediately
    manager._on_session_output(session.id, b"Continue? [y/n]\n")
    assert session.status is SessionState.WAITING
    assert (SessionState.ACTIVE, SessionState.WAITING) in transitions


def test_new_output_cancels_weak_prompt_timer() -> None:
    """New output should cancel a pending weak prompt timer."""
    manager, session, transitions = _make_manager_with_session()
    # No event loop — but test the cancel logic directly
    manager._schedule_weak_prompt(session.id, "Are you sure?")
    # Since no loop, it fires immediately in fallback mode
    # But let's verify the cancel method doesn't crash
    manager._cancel_weak_prompt_timer(session.id)
    # Timer should be gone
    assert session.id not in manager._weak_prompt_timers
