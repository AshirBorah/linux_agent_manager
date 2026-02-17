from __future__ import annotations

from tame.ui.widgets.search_dialog import SearchDialog, _ANSI_RE


def test_ansi_stripped_from_search() -> None:
    text = "\x1b[31mError:\x1b[0m something failed"
    clean = _ANSI_RE.sub("", text)
    assert clean == "Error: something failed"


def test_search_dialog_creates() -> None:
    """SearchDialog can be instantiated with session data."""
    sessions = [
        ("s1", "session-1", "line 1\nline 2\nError: failed\n"),
        ("s2", "session-2", "all good\nnothing here\n"),
    ]
    dialog = SearchDialog(sessions)
    assert dialog._sessions == sessions


def test_search_finds_results() -> None:
    """SearchDialog._search returns matching results."""
    sessions = [
        ("s1", "session-1", "line 1\nline 2\nError: failed\n"),
        ("s2", "session-2", "all good\nnothing here\n"),
    ]
    dialog = SearchDialog(sessions)
    results = dialog._search("Error")
    assert len(results) == 1
    assert results[0].session_id == "s1"
    assert results[0]._line_num == 3


def test_search_case_insensitive() -> None:
    sessions = [
        ("s1", "test", "Warning: something\n"),
    ]
    dialog = SearchDialog(sessions)
    results = dialog._search("warning")
    assert len(results) == 1


def test_search_no_results() -> None:
    sessions = [
        ("s1", "test", "all good\n"),
    ]
    dialog = SearchDialog(sessions)
    results = dialog._search("nonexistent")
    assert len(results) == 0


def test_search_multiple_sessions() -> None:
    sessions = [
        ("s1", "sess-1", "match here\n"),
        ("s2", "sess-2", "match here too\n"),
    ]
    dialog = SearchDialog(sessions)
    results = dialog._search("match")
    assert len(results) == 2
