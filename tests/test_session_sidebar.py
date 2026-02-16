from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tame.app import TAMEApp
from tame.session.output_buffer import OutputBuffer
from tame.session.pattern_matcher import PatternMatcher
from tame.session.session import Session
from tame.session.state import AttentionState, ProcessState
from tame.ui.widgets.session_list_item import SessionListItem
from textual.widgets import Label


_next_id = 0


def _make_session(app: TAMEApp, name: str) -> Session:
    global _next_id
    _next_id += 1
    session_id = f"test-session-{_next_id}"
    now = datetime.now(timezone.utc)
    session = Session(
        id=session_id,
        name=name,
        working_dir="/tmp",
        process_state=ProcessState.RUNNING,
        attention_state=AttentionState.NONE,
        created_at=now,
        last_activity=now,
        output_buffer=OutputBuffer(),
        pattern_matcher=PatternMatcher(app._session_manager._patterns),
        pid=123,
        pty_process=None,
    )
    app._session_manager._sessions[session_id] = session
    return session


@pytest.fixture(autouse=True)
def _reset_id():
    global _next_id
    _next_id = 0


@pytest.fixture
def app(tmp_path, monkeypatch) -> TAMEApp:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    app = TAMEApp()

    def _fake_create_session(
        name: str,
        working_dir: str,
        shell: str | None = None,
        command: list[str] | None = None,
    ) -> Session:
        del shell, command
        return _make_session(app, name)

    monkeypatch.setattr(app._session_manager, "create_session", _fake_create_session)
    monkeypatch.setattr(app._session_manager, "send_input", lambda _sid, _text: None)
    monkeypatch.setattr(
        app._session_manager, "resize_session", lambda _sid, _rows, _cols: None
    )
    monkeypatch.setattr(app, "_list_existing_tmux_sessions", lambda: [])
    return app


@pytest.mark.asyncio
async def test_search_filters_sessions(app: TAMEApp) -> None:
    """Typing in the search box hides non-matching sessions."""
    async with app.run_test() as pilot:
        app._create_session("alpha-project")
        app._create_session("beta-project")
        app._create_session("gamma-task")
        await pilot.pause()

        items = app.query(SessionListItem)
        assert len(items) == 3
        assert all(item.display for item in items)

        search = app.query_one("#session-search")
        search.value = "beta"
        await pilot.pause()

        visible = [i for i in app.query(SessionListItem) if i.display]
        hidden = [i for i in app.query(SessionListItem) if not i.display]
        assert len(visible) == 1
        assert visible[0]._session_name == "beta-project"
        assert len(hidden) == 2


@pytest.mark.asyncio
async def test_search_shows_no_results_label(app: TAMEApp) -> None:
    """When no sessions match the query, a 'No matching sessions' label appears."""
    async with app.run_test() as pilot:
        app._create_session("alpha-project")
        await pilot.pause()

        no_results = app.query_one("#no-results", Label)
        assert not no_results.display

        search = app.query_one("#session-search")
        search.value = "zzz-nonexistent"
        await pilot.pause()

        assert no_results.display

        search.value = ""
        await pilot.pause()

        assert not no_results.display


@pytest.mark.asyncio
async def test_search_clear_restores_all(app: TAMEApp) -> None:
    """Clearing the search box makes all sessions visible again."""
    async with app.run_test() as pilot:
        app._create_session("alpha-project")
        app._create_session("beta-project")
        await pilot.pause()

        search = app.query_one("#session-search")
        search.value = "alpha"
        await pilot.pause()
        assert sum(1 for i in app.query(SessionListItem) if i.display) == 1

        search.value = ""
        await pilot.pause()
        assert sum(1 for i in app.query(SessionListItem) if i.display) == 2


@pytest.mark.asyncio
async def test_search_is_case_insensitive(app: TAMEApp) -> None:
    """Search filtering is case-insensitive."""
    async with app.run_test() as pilot:
        app._create_session("MyProject")
        await pilot.pause()

        search = app.query_one("#session-search")
        search.value = "myproject"
        await pilot.pause()

        visible = [i for i in app.query(SessionListItem) if i.display]
        assert len(visible) == 1
        assert visible[0]._session_name == "MyProject"
