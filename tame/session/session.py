from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .output_buffer import OutputBuffer
from .pattern_matcher import PatternMatcher
from .pty_process import PTYProcess
from .state import AttentionState, ProcessState, SessionState, compute_session_state


@dataclass
class UsageInfo:
    """Parsed AI model usage data for a session."""

    model_name: str = ""
    messages_used: int | None = None
    tokens_used: int | None = None
    quota_remaining: str = ""
    refresh_time: str = ""
    raw_text: str = ""


@dataclass
class Session:
    id: str  # UUID
    name: str  # User-editable display name
    working_dir: str  # CWD for the shell
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
    usage: UsageInfo = field(default_factory=UsageInfo)
    profile: str = ""
    group: str = ""

    @property
    def status(self) -> SessionState:
        """Derived display state for backward compatibility."""
        return compute_session_state(self.process_state, self.attention_state)
