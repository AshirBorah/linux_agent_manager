from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class Worktree:
    """Represents a git worktree."""

    path: str
    branch: str
    head: str  # commit hash
    is_main: bool = False


def list_worktrees(repo_dir: str) -> list[Worktree]:
    """List all worktrees for a git repository."""
    try:
        proc = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except Exception as exc:
        log.warning("Failed to list worktrees: %s", exc)
        return []

    if proc.returncode != 0:
        return []

    worktrees: list[Worktree] = []
    path = ""
    head = ""
    branch = ""
    for line in proc.stdout.splitlines():
        if line.startswith("worktree "):
            if path:
                worktrees.append(Worktree(path=path, branch=branch, head=head))
            path = line[9:]
            head = ""
            branch = ""
        elif line.startswith("HEAD "):
            head = line[5:]
        elif line.startswith("branch "):
            ref = line[7:]
            # Strip refs/heads/ prefix
            if ref.startswith("refs/heads/"):
                branch = ref[11:]
            else:
                branch = ref
    if path:
        worktrees.append(Worktree(path=path, branch=branch, head=head))

    # Mark the first worktree as main
    if worktrees:
        worktrees[0].is_main = True

    return worktrees


def create_worktree(
    repo_dir: str,
    branch: str,
    worktree_path: str | None = None,
    new_branch: bool = False,
) -> tuple[str, str]:
    """Create a new git worktree.

    Returns (worktree_path, error_message). On success, error is empty.
    """
    if worktree_path is None:
        # Default: sibling directory named after branch
        parent = os.path.dirname(os.path.abspath(repo_dir))
        safe_branch = branch.replace("/", "-")
        worktree_path = os.path.join(parent, safe_branch)

    cmd = ["git", "worktree", "add"]
    if new_branch:
        cmd.extend(["-b", branch, worktree_path])
    else:
        cmd.extend([worktree_path, branch])

    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except Exception as exc:
        return ("", str(exc))

    if proc.returncode != 0:
        return ("", proc.stderr.strip())

    return (worktree_path, "")


def remove_worktree(repo_dir: str, worktree_path: str, force: bool = False) -> str:
    """Remove a git worktree. Returns error message or empty string on success."""
    cmd = ["git", "worktree", "remove"]
    if force:
        cmd.append("--force")
    cmd.append(worktree_path)

    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except Exception as exc:
        return str(exc)

    if proc.returncode != 0:
        return proc.stderr.strip()
    return ""
