from __future__ import annotations

from unittest.mock import patch, MagicMock
import subprocess

from tame.git.worktree import Worktree, list_worktrees, create_worktree, remove_worktree


PORCELAIN_OUTPUT = """\
worktree /home/user/project
HEAD abc123
branch refs/heads/main

worktree /home/user/feat-login
HEAD def456
branch refs/heads/feat/login

"""


@patch("tame.git.worktree.subprocess.run")
def test_list_worktrees_parses_porcelain(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(
        returncode=0, stdout=PORCELAIN_OUTPUT
    )
    result = list_worktrees("/repo")
    assert len(result) == 2
    assert result[0].path == "/home/user/project"
    assert result[0].branch == "main"
    assert result[0].head == "abc123"
    assert result[0].is_main is True
    assert result[1].path == "/home/user/feat-login"
    assert result[1].branch == "feat/login"
    assert result[1].is_main is False


@patch("tame.git.worktree.subprocess.run")
def test_list_worktrees_empty_on_failure(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
    result = list_worktrees("/repo")
    assert result == []


@patch("tame.git.worktree.subprocess.run")
def test_list_worktrees_handles_exception(mock_run: MagicMock) -> None:
    mock_run.side_effect = Exception("not a git repo")
    result = list_worktrees("/repo")
    assert result == []


@patch("tame.git.worktree.subprocess.run")
def test_create_worktree_new_branch(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    path, err = create_worktree("/repo", "feat/new", new_branch=True)
    assert err == ""
    assert "feat-new" in path  # branch slashes replaced with dashes
    cmd = mock_run.call_args[0][0]
    assert cmd[:3] == ["git", "worktree", "add"]
    assert "-b" in cmd


@patch("tame.git.worktree.subprocess.run")
def test_create_worktree_existing_branch(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    path, err = create_worktree("/repo", "feat/existing", new_branch=False)
    assert err == ""
    assert path != ""
    cmd = mock_run.call_args[0][0]
    assert "-b" not in cmd


@patch("tame.git.worktree.subprocess.run")
def test_create_worktree_returns_error(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(
        returncode=1, stdout="", stderr="fatal: already exists"
    )
    path, err = create_worktree("/repo", "feat/dup")
    assert path == ""
    assert "already exists" in err


@patch("tame.git.worktree.subprocess.run")
def test_create_worktree_custom_path(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    path, err = create_worktree(
        "/repo", "feat/custom", worktree_path="/tmp/my-worktree"
    )
    assert err == ""
    assert path == "/tmp/my-worktree"


@patch("tame.git.worktree.subprocess.run")
def test_create_worktree_handles_exception(mock_run: MagicMock) -> None:
    mock_run.side_effect = OSError("disk full")
    path, err = create_worktree("/repo", "feat/fail")
    assert path == ""
    assert "disk full" in err


@patch("tame.git.worktree.subprocess.run")
def test_remove_worktree_success(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    err = remove_worktree("/repo", "/home/user/feat-login")
    assert err == ""


@patch("tame.git.worktree.subprocess.run")
def test_remove_worktree_force(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    err = remove_worktree("/repo", "/home/user/feat-login", force=True)
    assert err == ""
    cmd = mock_run.call_args[0][0]
    assert "--force" in cmd


@patch("tame.git.worktree.subprocess.run")
def test_remove_worktree_returns_error(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(
        returncode=1, stdout="", stderr="fatal: not a worktree"
    )
    err = remove_worktree("/repo", "/home/user/gone")
    assert "not a worktree" in err


@patch("tame.git.worktree.subprocess.run")
def test_remove_worktree_handles_exception(mock_run: MagicMock) -> None:
    mock_run.side_effect = OSError("permission denied")
    err = remove_worktree("/repo", "/home/user/locked")
    assert "permission denied" in err
