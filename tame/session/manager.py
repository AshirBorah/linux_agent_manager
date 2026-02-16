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
from .session import Session
from .state import SessionState

_INPUT_RESETS = frozenset({SessionState.ERROR, SessionState.WAITING})

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
            status=SessionState.ACTIVE,
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
        del self._sessions[session_id]

    def get_session(self, session_id: str) -> Session:
        return self._get(session_id)

    def list_sessions(self) -> list[Session]:
        return list(self._sessions.values())

    # ------------------------------------------------------------------
    # Session control
    # ------------------------------------------------------------------

    def pause_session(self, session_id: str) -> None:
        session = self._get(session_id)
        if session.pty_process and session.pty_process.is_alive:
            session.pty_process.pause()
            self._set_status(session, SessionState.PAUSED)

    def resume_session(self, session_id: str) -> None:
        session = self._get(session_id)
        if session.pty_process and session.pty_process.is_alive:
            session.pty_process.resume()
            self._set_status(session, SessionState.ACTIVE)

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
                self._set_status(session, SessionState.DONE)

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def send_input(self, session_id: str, text: str) -> None:
        session = self._get(session_id)
        if session.pty_process is None:
            raise RuntimeError(f"Session {session_id} has no PTY process")
        session.pty_process.write(text)
        session.last_activity = datetime.now(timezone.utc)
        if session.status in _INPUT_RESETS:
            self._set_status(session, SessionState.ACTIVE)

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
            new_state = (
                SessionState.DONE if exit_code == 0 else SessionState.ERROR
            )
            self._set_status(session, new_state)
            return

        text = data.decode("utf-8", errors="replace")
        session.output_buffer.append_data(text)
        session.last_activity = datetime.now(timezone.utc)

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
                self._set_status(session, SessionState.ERROR, line.strip())
            elif match.category == "prompt":
                self._set_status(session, SessionState.WAITING, line.strip())
            elif match.category == "completion":
                self._set_status(session, SessionState.DONE, line.strip())
            # progress is informational — no status change

        # Some interactive CLIs print prompts without trailing newline.
        partial = self._scan_partials.get(session_id, "")
        if partial:
            partial_match = session.pattern_matcher.scan(partial)
            if partial_match and partial_match.category == "prompt":
                self._set_status(session, SessionState.WAITING, partial.strip())

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
            self._set_status(session, SessionState.ERROR, last_match.line.strip())
        elif last_match.category == "prompt":
            self._set_status(session, SessionState.WAITING, last_match.line.strip())
        elif last_match.category == "completion":
            self._set_status(session, SessionState.DONE, last_match.line.strip())

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
    # Cleanup
    # ------------------------------------------------------------------

    def close_all(self) -> None:
        for session in list(self._sessions.values()):
            if session.pty_process:
                session.pty_process.close()
        self._sessions.clear()
        self._scan_partials.clear()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get(self, session_id: str) -> Session:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise KeyError(f"No session with id {session_id!r}") from None

    def _set_status(
        self, session: Session, new_state: SessionState, matched_text: str = ""
    ) -> None:
        old_state = session.status
        if old_state is new_state:
            return
        session.status = new_state
        if self._on_status_change:
            self._on_status_change(session.id, old_state, new_state, matched_text)
