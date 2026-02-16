from __future__ import annotations

import re
from dataclasses import dataclass


# Priority order for scanning — earlier categories win on ties.
SCAN_ORDER: list[str] = ["error", "prompt", "completion", "progress"]


@dataclass(frozen=True, slots=True)
class PatternMatch:
    category: str
    pattern_index: int
    matched_text: str
    line: str


class PatternMatcher:
    def __init__(self, patterns: dict[str, list[str]]) -> None:
        # Compile once.  Stored as category -> list[(index, compiled_re)].
        self._compiled: dict[str, list[tuple[int, re.Pattern[str]]]] = {}
        for category, raw_patterns in patterns.items():
            self._compiled[category] = [
                (i, re.compile(p, re.IGNORECASE))
                for i, p in enumerate(raw_patterns)
            ]

    def scan(self, line: str) -> PatternMatch | None:
        for category in SCAN_ORDER:
            compiled = self._compiled.get(category, [])
            for idx, rx in compiled:
                m = rx.search(line)
                if m:
                    return PatternMatch(
                        category=category,
                        pattern_index=idx,
                        matched_text=m.group(),
                        line=line,
                    )
        # Check any categories not in SCAN_ORDER (user-defined extras).
        for category, compiled in self._compiled.items():
            if category in SCAN_ORDER:
                continue
            for idx, rx in compiled:
                m = rx.search(line)
                if m:
                    return PatternMatch(
                        category=category,
                        pattern_index=idx,
                        matched_text=m.group(),
                        line=line,
                    )
        return None
