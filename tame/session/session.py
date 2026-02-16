from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .output_buffer import OutputBuffer
from .pattern_matcher import PatternMatcher
from .pty_process import PTYProcess
from .state import SessionState


@dataclass
class Session:
    id: str                            # UUID
    name: str                          # User-editable display name
    working_dir: str                   # CWD for the shell
    status: SessionState
    created_at: datetime
    last_activity: datetime
    output_buffer: OutputBuffer
    pattern_matcher: PatternMatcher
    pid: int | None = None
    exit_code: int | None = None
    input_history: list[str] = field(default_factory=list)
    pty_process: PTYProcess | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
