from __future__ import annotations

from datetime import datetime, timezone

import pytest

from lam.app import LAMApp
from lam.session.output_buffer import OutputBuffer
from lam.session.pattern_matcher import PatternMatcher
from lam.session.session import Session
from lam.session.state import SessionState
from lam.ui.widgets.session_list_item import SessionListItem


@pytest.fixture
def app(tmp_path, monkeypatch) -> LAMApp:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    app = LAMApp()

    def _fake_create_session(
        name: str,
        working_dir: str,
        shell: str | None = None,
        command: list[str] | None = None,
    ) -> Session:
        del shell, command
        now = datetime.now(timezone.utc)
        session_id = "test-session-1"
        output_buffer = OutputBuffer()
        session = Session(
            id=session_id,
            name=name,
            working_dir=working_dir,
            status=SessionState.ACTIVE,
            created_at=now,
            last_activity=now,
            output_buffer=output_buffer,
            pattern_matcher=PatternMatcher(app._session_manager._patterns),
            pid=123,
            pty_process=None,
        )
        app._session_manager._sessions[session_id] = session
        return session

    monkeypatch.setattr(app._session_manager, "create_session", _fake_create_session)
    monkeypatch.setattr(app._session_manager, "send_input", lambda _sid, _text: None)
    monkeypatch.setattr(app._session_manager, "resize_session", lambda _sid, _rows, _cols: None)
    monkeypatch.setattr(app, "_list_existing_tmux_sessions", lambda: [])
    return app


@pytest.mark.asyncio
async def test_session_list_item_renders_name_and_status(app: LAMApp) -> None:
    async with app.run_test() as pilot:
        app._create_session("session-visible")
        await pilot.pause()
        item = app.query_one(SessionListItem)
        rendered = item.render()
        assert "session-visible" in rendered.plain
        assert "ACTIVE" in rendered.plain
