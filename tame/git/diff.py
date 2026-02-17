from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class DiffResult:
    """Result of a git diff operation."""

    diff_text: str
    files_changed: int
    insertions: int
    deletions: int
    error: str = ""


def git_diff(
    working_dir: str,
    staged: bool = False,
    ref: str | None = None,
) -> DiffResult:
    """Run ``git diff`` and return the result.

    Parameters
    ----------
    working_dir:
        Directory to run git in.
    staged:
        If ``True``, show staged changes (``--cached``).
    ref:
        Optional ref to diff against (e.g., ``HEAD~1``, ``main``).
    """
    cmd = ["git", "diff", "--no-color"]
    if staged:
        cmd.append("--cached")
    if ref:
        cmd.append(ref)

    try:
        proc = subprocess.run(
            cmd,
            cwd=working_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except Exception as exc:
        return DiffResult(diff_text="", files_changed=0, insertions=0, deletions=0, error=str(exc))

    if proc.returncode != 0:
        return DiffResult(
            diff_text="",
            files_changed=0,
            insertions=0,
            deletions=0,
            error=proc.stderr.strip(),
        )

    diff_text = proc.stdout

    # Parse stat
    files_changed = 0
    insertions = 0
    deletions = 0
    stat_cmd = cmd + ["--stat"]
    try:
        stat_proc = subprocess.run(
            stat_cmd,
            cwd=working_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if stat_proc.returncode == 0:
            for line in stat_proc.stdout.splitlines():
                if "file" in line and "changed" in line:
                    parts = line.split(",")
                    for part in parts:
                        part = part.strip()
                        if "file" in part:
                            try:
                                files_changed = int(part.split()[0])
                            except (ValueError, IndexError):
                                pass
                        elif "insertion" in part:
                            try:
                                insertions = int(part.split()[0])
                            except (ValueError, IndexError):
                                pass
                        elif "deletion" in part:
                            try:
                                deletions = int(part.split()[0])
                            except (ValueError, IndexError):
                                pass
    except Exception:
        pass

    return DiffResult(
        diff_text=diff_text,
        files_changed=files_changed,
        insertions=insertions,
        deletions=deletions,
    )


def git_status(working_dir: str) -> str:
    """Run ``git status --short`` and return the output."""
    try:
        proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        return proc.stdout if proc.returncode == 0 else proc.stderr
    except Exception as exc:
        return str(exc)
