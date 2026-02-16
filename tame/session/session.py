from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .output_buffer import OutputBuffer
from .pattern_matcher import PatternMatcher
from .pty_process import PTYProcess
from .state import AttentionState, ProcessState, SessionState, compute_session_state


@dataclass
class Session:
    id: str                            # UUID
    name: str                          # User-editable display name
    working_dir: str                   # CWD for the shell
    process_state: ProcessState
    attention_state: AttentionState
    created_at: datetime
    last_activity: datetime
    output_buffer: OutputBuffer
    pattern_matcher: PatternMatcher
    pid: int | None = None
    exit_code: int | None = None
    input_history: list[str] = field(default_factory=list)
    pty_process: PTYProcess | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> SessionState:
        """Derived display state for backward compatibility."""
        return compute_session_state(self.process_state, self.attention_state)
