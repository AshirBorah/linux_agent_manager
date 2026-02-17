from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Label, Static

from tame.git.diff import DiffResult


class DiffLine(Static):
    """A single line of diff output with syntax-aware coloring."""

    DEFAULT_CSS = """
    DiffLine {
        width: 100%;
        height: auto;
    }

    DiffLine.diff-add {
        color: #22c55e;
    }

    DiffLine.diff-del {
        color: #ef4444;
    }

    DiffLine.diff-hunk {
        color: #60a5fa;
    }

    DiffLine.diff-file {
        color: #f59e0b;
        text-style: bold;
    }
    """


class DiffViewer(ModalScreen[None]):
    """Modal viewer for git diff output."""

    DEFAULT_CSS = """
    DiffViewer {
        align: center middle;
    }

    DiffViewer #diff-box {
        width: 90%;
        height: 80%;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    DiffViewer #diff-header {
        height: 2;
    }

    DiffViewer #diff-scroll {
        height: 1fr;
    }
    """

    def __init__(self, diff_result: DiffResult, title: str = "Git Diff") -> None:
        super().__init__()
        self._diff = diff_result
        self._title = title

    def compose(self) -> ComposeResult:
        with Vertical(id="diff-box"):
            stats = (
                f"{self._title}  |  "
                f"{self._diff.files_changed} file(s), "
                f"+{self._diff.insertions} -{self._diff.deletions}  "
                f"[Esc to close]"
            )
            yield Label(stats, id="diff-header")
            with VerticalScroll(id="diff-scroll"):
                if self._diff.error:
                    yield Label(f"Error: {self._diff.error}")
                elif not self._diff.diff_text.strip():
                    yield Label("No changes detected.")
                else:
                    for line in self._diff.diff_text.split("\n"):
                        dl = DiffLine(line)
                        if line.startswith("+++") or line.startswith("---"):
                            dl.add_class("diff-file")
                        elif line.startswith("+"):
                            dl.add_class("diff-add")
                        elif line.startswith("-"):
                            dl.add_class("diff-del")
                        elif line.startswith("@@"):
                            dl.add_class("diff-hunk")
                        yield dl

    def key_escape(self) -> None:
        self.dismiss(None)

    def key_q(self) -> None:
        self.dismiss(None)
