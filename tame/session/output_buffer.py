from __future__ import annotations

from collections import deque


class OutputBuffer:
    def __init__(self, maxlen: int = 10_000) -> None:
        self._lines: deque[str] = deque(maxlen=maxlen)
        self._partial: str = ""
        self.total_lines_received: int = 0
        self.total_bytes_received: int = 0

    @property
    def maxlen(self) -> int:
        assert self._lines.maxlen is not None
        return self._lines.maxlen

    def append_data(self, text: str) -> None:
        self.total_bytes_received += len(text)

        combined = self._partial + text
        parts = combined.split("\n")

        # Everything except the last element is a complete line.
        # The last element is a partial (possibly empty if text ended with \n).
        for complete_line in parts[:-1]:
            self._lines.append(complete_line)
            self.total_lines_received += 1

        self._partial = parts[-1]

    def get_lines(self) -> list[str]:
        return list(self._lines)

    def get_all_text(self) -> str:
        pieces = list(self._lines)
        if pieces or self._partial:
            # Join complete lines with newlines, then append partial if present
            text = "\n".join(pieces)
            if pieces and self._partial:
                text += "\n" + self._partial
            elif self._partial:
                text = self._partial
            return text
        return ""

    def clear(self) -> None:
        self._lines.clear()
        self._partial = ""
        self.total_lines_received = 0
        self.total_bytes_received = 0
