from __future__ import annotations

import asyncio
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Callable

from tame.config.defaults import get_default_patterns_flat

from .output_buffer import OutputBuffer
from .pattern_matcher import PatternMatcher, PatternMatch
from .pty_process import PTYProcess
from .session import Session, UsageInfo
from .state import AttentionState, ProcessState, SessionState

# Built-in usage patterns for common AI CLIs
_USAGE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Claude Code: "Opus messages: 42/100 remaining"
    ("messages_used", re.compile(r"(\w+)\s+messages?:\s*(\d+)/(\d+)\s*remaining", re.IGNORECASE)),
    # Generic token count: "Tokens used: 12345" or "tokens: 12,345"
    ("tokens_used", re.compile(r"tokens?\s*(?:used)?:\s*([\d,]+)", re.IGNORECASE)),
    # Model name: "Model: claude-3-opus" or "Using model: gpt-4"
    ("model_name", re.compile(r"(?:using\s+)?model:\s*(\S+)", re.IGNORECASE)),
    # Reset/refresh time: "Resets in 2h 30m" or "Refresh: 3:00 PM"
    ("refresh_time", re.compile(r"(?:resets?\s+in|refresh(?:es)?(?:\s+(?:at|in))?)\s*:?\s*(.+)", re.IGNORECASE)),
]

StatusChangeCallback = Callable[[str, SessionState, SessionState, str], None]
OutputCallback = Callable[[str, str], None]  # session_id, text

ANSI_ESCAPE_RE = re.compile(
    r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x1B\x07]*(?:\x07|\x1B\\))"
)


class SessionManager:
    def __init__(
        self,
        on_status_change: StatusChangeCallback | None = None,
        on_output: OutputCallback | None = None,
        patterns: dict[str, list[str]] | None = None,
        idle_threshold_seconds: float = 300.0,
        idle_check_interval: float = 30.0,
        idle_prompt_timeout: float = 3.0,
    ) -> None:
        self._sessions: dict[str, Session] = {}
        self._scan_partials: dict[str, str] = {}
        self._on_status_change = on_status_change
        self._on_output = on_output
        base = get_default_patterns_flat()
        if patterns:
            base.update({cat: list(rxs) for cat, rxs in patterns.items()})
        self._patterns: dict[str, list[str]] = base
        self._loop: asyncio.AbstractEventLoop | None = None
        self._idle_threshold: float = idle_threshold_seconds
        self._idle_check_interval: float = idle_check_interval
        self._idle_prompt_timeout: float = idle_prompt_timeout
        self._idle_checker_task: asyncio.Task | None = None
        # Cache last-scanned partial to avoid redundant regex work (#19)
        self._last_scanned_partial: dict[str, str] = {}
        # Pending weak prompt timers — session_id -> asyncio.TimerHandle
        self._weak_prompt_timers: dict[str, asyncio.TimerHandle] = {}

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_session(
        self,
        name: str,
        working_dir: str,
        shell: str | None = None,
        command: list[str] | None = None,
    ) -> Session:
        shell = shell or os.environ.get("SHELL", "/bin/bash")
        session_id = uuid.uuid4().hex

        pty_proc = PTYProcess()
        pty_proc.start(shell=shell, cwd=working_dir, command=command)

        now = datetime.now(timezone.utc)
        session = Session(
            id=session_id,
            name=name,
            working_dir=working_dir,
            process_state=ProcessState.RUNNING,
            attention_state=AttentionState.NONE,
            created_at=now,
            last_activity=now,
            output_buffer=OutputBuffer(),
            pattern_matcher=PatternMatcher(self._patterns),
            pid=pty_proc.pid,
            pty_process=pty_proc,
        )
        self._sessions[session_id] = session

        if self._loop:
            pty_proc.attach_to_loop(
                self._loop,
                lambda data, sid=session_id: self._on_session_output(sid, data),
            )

        return session

    def delete_session(self, session_id: str) -> None:
        session = self._get(session_id)
        if session.pty_process:
            session.pty_process.close()
        self._scan_partials.pop(session_id, None)
        self._last_scanned_partial.pop(session_id, None)
        self._cancel_weak_prompt_timer(session_id)
        del self._sessions[session_id]

    def get_session(self, session_id: str) -> Session:
        return self._get(session_id)

    def rename_session(self, session_id: str, new_name: str) -> None:
        """Rename an existing session."""
        session = self._get(session_id)
        session.name = new_name

    def list_sessions(self) -> list[Session]:
        return list(self._sessions.values())

    # ------------------------------------------------------------------
    # Session control
    # ------------------------------------------------------------------

    def pause_session(self, session_id: str) -> None:
        session = self._get(session_id)
        if session.pty_process and session.pty_process.is_alive:
            session.pty_process.pause()
            self._set_process_state(session, ProcessState.PAUSED)

    def resume_session(self, session_id: str) -> None:
        session = self._get(session_id)
        if session.pty_process and session.pty_process.is_alive:
            session.pty_process.resume()
            self._set_process_state(session, ProcessState.RUNNING)

    def pause_all(self) -> None:
        for sid in list(self._sessions):
            try:
                self.pause_session(sid)
            except (KeyError, RuntimeError):
                pass

    def resume_all(self) -> None:
        for sid in list(self._sessions):
            try:
                self.resume_session(sid)
            except (KeyError, RuntimeError):
                pass

    def stop_all(self) -> None:
        for session in list(self._sessions.values()):
            if session.pty_process and session.pty_process.is_alive:
                session.pty_process.terminate()
                self._set_process_state(session, ProcessState.EXITED)

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def send_input(self, session_id: str, text: str) -> None:
        session = self._get(session_id)
        if session.pty_process is None:
            raise RuntimeError(f"Session {session_id} has no PTY process")
        session.pty_process.write(text)
        session.last_activity = datetime.now(timezone.utc)
        # Clear attention on user input (#5, #6)
        if session.attention_state in (
            AttentionState.NEEDS_INPUT,
            AttentionState.ERROR_SEEN,
            AttentionState.IDLE,
        ):
            self._set_attention_state(session, AttentionState.NONE)

    def resize_session(self, session_id: str, rows: int, cols: int) -> None:
        session = self._get(session_id)
        if session.pty_process is None:
            raise RuntimeError(f"Session {session_id} has no PTY process")
        session.pty_process.resize(rows, cols)

    def _on_session_output(self, session_id: str, data: bytes) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return

        if not data:
            # EOF — process exited.
            self._scan_partials.pop(session_id, None)
            exit_code = (
                session.pty_process.exit_code
                if session.pty_process
                else None
            )
            session.exit_code = exit_code
            if exit_code != 0:
                self._set_attention_state(session, AttentionState.ERROR_SEEN)
            self._set_process_state(session, ProcessState.EXITED)
            return

        text = data.decode("utf-8", errors="replace")
        session.output_buffer.append_data(text)
        session.last_activity = datetime.now(timezone.utc)

        # New output clears IDLE attention
        if session.attention_state is AttentionState.IDLE:
            self._set_attention_state(session, AttentionState.NONE)

        # Cancel any pending weak prompt timer — new output arrived (#7)
        self._cancel_weak_prompt_timer(session_id)

        if self._on_output:
            self._on_output(session_id, text)

        # Run pattern matcher on each complete line, preserving split lines
        # across PTY read boundaries.
        cleaned = ANSI_ESCAPE_RE.sub("", text)
        combined = self._scan_partials.get(session_id, "") + cleaned
        parts = combined.split("\n")
        complete_lines = parts[:-1]
        self._scan_partials[session_id] = parts[-1]

        for line in complete_lines:
            if not line:
                continue
            match: PatternMatch | None = session.pattern_matcher.scan(line)
            if match is None:
                continue
            if match.category == "error":
                self._set_attention_state(session, AttentionState.ERROR_SEEN, line.strip())
            elif match.category == "prompt":
                self._set_attention_state(session, AttentionState.NEEDS_INPUT, line.strip())
            elif match.category == "weak_prompt":
                self._schedule_weak_prompt(session_id, line.strip())
            elif match.category == "completion":
                self._set_process_state(session, ProcessState.EXITED, line.strip())
            # progress is informational — no status change

        # Some interactive CLIs print prompts without trailing newline.
        # Cache last-scanned partial to avoid redundant regex work (#19).
        partial = self._scan_partials.get(session_id, "")
        if partial and partial != self._last_scanned_partial.get(session_id):
            self._last_scanned_partial[session_id] = partial
            partial_match = session.pattern_matcher.scan(partial)
            if partial_match and partial_match.category == "prompt":
                self._set_attention_state(session, AttentionState.NEEDS_INPUT, partial.strip())
            elif partial_match and partial_match.category == "weak_prompt":
                self._schedule_weak_prompt(session_id, partial.strip())

        # Scan for usage/quota info (#20)
        for line in complete_lines:
            if line:
                self._scan_usage(session, line)

    # ------------------------------------------------------------------
    # Usage/quota parsing (#20)
    # ------------------------------------------------------------------

    def _scan_usage(self, session: Session, line: str) -> None:
        """Check a line for usage/quota patterns and update session.usage."""
        cleaned = ANSI_ESCAPE_RE.sub("", line)
        for kind, rx in _USAGE_PATTERNS:
            m = rx.search(cleaned)
            if m is None:
                continue
            if kind == "messages_used":
                session.usage.model_name = m.group(1)
                used = int(m.group(2))
                total = int(m.group(3))
                session.usage.messages_used = total - int(m.group(3)) + used
                session.usage.quota_remaining = f"{m.group(3)} of {total}"
                session.usage.raw_text = m.group(0)
            elif kind == "tokens_used":
                session.usage.tokens_used = int(m.group(1).replace(",", ""))
                session.usage.raw_text = m.group(0)
            elif kind == "model_name":
                session.usage.model_name = m.group(1)
            elif kind == "refresh_time":
                session.usage.refresh_time = m.group(1).strip()

    # ------------------------------------------------------------------
    # Weak prompt timeout gating (#7)
    # ------------------------------------------------------------------

    def _schedule_weak_prompt(self, session_id: str, matched_line: str) -> None:
        """Schedule a delayed NEEDS_INPUT transition for a weak prompt match.

        If no new output arrives within ``_idle_prompt_timeout`` seconds the
        session will transition to WAITING.  Any new output cancels the timer.
        """
        self._cancel_weak_prompt_timer(session_id)
        if self._loop is None:
            # No event loop — fire immediately (unit-test fallback)
            session = self._sessions.get(session_id)
            if session:
                self._set_attention_state(session, AttentionState.NEEDS_INPUT, matched_line)
            return
        handle = self._loop.call_later(
            self._idle_prompt_timeout,
            self._fire_weak_prompt,
            session_id,
            matched_line,
        )
        self._weak_prompt_timers[session_id] = handle

    def _fire_weak_prompt(self, session_id: str, matched_line: str) -> None:
        """Callback fired after idle_prompt_timeout — set NEEDS_INPUT."""
        self._weak_prompt_timers.pop(session_id, None)
        session = self._sessions.get(session_id)
        if session is None:
            return
        # Only fire if still RUNNING with no other attention
        if (
            session.process_state is ProcessState.RUNNING
            and session.attention_state is AttentionState.NONE
        ):
            self._set_attention_state(session, AttentionState.NEEDS_INPUT, matched_line)

    def _cancel_weak_prompt_timer(self, session_id: str) -> None:
        """Cancel a pending weak prompt timer for the given session."""
        handle = self._weak_prompt_timers.pop(session_id, None)
        if handle is not None:
            handle.cancel()

    # ------------------------------------------------------------------
    # Pane content scanning (for tmux restore)
    # ------------------------------------------------------------------

    def scan_pane_content(self, session_id: str, text: str) -> None:
        """Scan captured pane text and update session status.

        Unlike ``_on_session_output``, this does **not** append to the
        output buffer or trigger UI output — it only sets status based
        on the last matching pattern found in *text*.
        """
        session = self._get(session_id)
        cleaned = ANSI_ESCAPE_RE.sub("", text)
        lines = cleaned.split("\n")

        last_match: PatternMatch | None = None
        for line in lines:
            if not line.strip():
                continue
            match = session.pattern_matcher.scan(line)
            if match:
                last_match = match

        # Check final non-empty line as a partial (prompts often lack
        # a trailing newline).
        for line in reversed(lines):
            stripped = line.strip()
            if stripped:
                match = session.pattern_matcher.scan(stripped)
                if match and match.category == "prompt":
                    last_match = match
                break

        if last_match is None:
            return
        if last_match.category == "error":
            self._set_attention_state(session, AttentionState.ERROR_SEEN, last_match.line.strip())
        elif last_match.category == "prompt":
            self._set_attention_state(session, AttentionState.NEEDS_INPUT, last_match.line.strip())
        elif last_match.category == "completion":
            self._set_process_state(session, ProcessState.EXITED, last_match.line.strip())

    # ------------------------------------------------------------------
    # Event loop integration
    # ------------------------------------------------------------------

    def attach_to_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        for session_id, session in self._sessions.items():
            if session.pty_process and session.pty_process.is_alive:
                session.pty_process.attach_to_loop(
                    loop,
                    lambda data, sid=session_id: self._on_session_output(
                        sid, data
                    ),
                )

    # ------------------------------------------------------------------
    # Idle detection (#6)
    # ------------------------------------------------------------------

    def start_idle_checker(self) -> None:
        """Start an async periodic task that checks for idle sessions."""
        if self._idle_checker_task is not None:
            return
        if self._loop is None:
            return
        self._idle_checker_task = self._loop.create_task(self._idle_check_loop())

    def stop_idle_checker(self) -> None:
        """Cancel the idle checker task."""
        if self._idle_checker_task is not None:
            self._idle_checker_task.cancel()
            self._idle_checker_task = None

    async def _idle_check_loop(self) -> None:
        """Periodically check sessions for inactivity."""
        while True:
            await asyncio.sleep(self._idle_check_interval)
            self._check_idle_sessions()

    def _check_idle_sessions(self) -> None:
        """Transition running sessions to IDLE if inactive beyond threshold."""
        now = datetime.now(timezone.utc)
        for session in self._sessions.values():
            if session.process_state is not ProcessState.RUNNING:
                continue
            if session.attention_state is not AttentionState.NONE:
                continue
            elapsed = (now - session.last_activity).total_seconds()
            if elapsed >= self._idle_threshold:
                self._set_attention_state(session, AttentionState.IDLE)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close_all(self) -> None:
        self.stop_idle_checker()
        for sid in list(self._weak_prompt_timers):
            self._cancel_weak_prompt_timer(sid)
        for session in list(self._sessions.values()):
            if session.pty_process:
                session.pty_process.close()
        self._sessions.clear()
        self._scan_partials.clear()
        self._last_scanned_partial.clear()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get(self, session_id: str) -> Session:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise KeyError(f"No session with id {session_id!r}") from None

    def _set_process_state(
        self, session: Session, new_ps: ProcessState, matched_text: str = ""
    ) -> None:
        old_status = session.status
        session.process_state = new_ps
        new_status = session.status
        if old_status is not new_status and self._on_status_change:
            self._on_status_change(session.id, old_status, new_status, matched_text)

    def _set_attention_state(
        self, session: Session, new_as: AttentionState, matched_text: str = ""
    ) -> None:
        old_status = session.status
        session.attention_state = new_as
        new_status = session.status
        if old_status is not new_status and self._on_status_change:
            self._on_status_change(session.id, old_status, new_status, matched_text)
