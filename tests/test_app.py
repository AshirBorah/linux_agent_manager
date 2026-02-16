"""Smoke tests for the LAMApp TUI using Textual's async pilot."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from textual import events
from textual.widgets import Input

from lam.app import LAMApp
from lam.session.output_buffer import OutputBuffer
from lam.session.pattern_matcher import PatternMatcher
from lam.session.session import Session
from lam.session.state import SessionState
from lam.ui.widgets import (
    HeaderBar,
    SessionSidebar,
    SessionViewer,
    StatusBar,
    ToastOverlay,
)
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
        session_id = f"test-session-{len(app._session_manager._sessions) + 1}"
        now = datetime.now(timezone.utc)
        output_buffer = OutputBuffer()
        output_buffer.append_data("$ ready\n")
        session = Session(
            id=session_id,
            name=name,
            working_dir=working_dir,
            status=SessionState.ACTIVE,
            created_at=now,
            last_activity=now,
            output_buffer=output_buffer,
            pattern_matcher=PatternMatcher(app._session_manager._patterns),
            pid=999,
            pty_process=None,
        )
        app._session_manager._sessions[session_id] = session
        return session

    monkeypatch.setattr(app._session_manager, "create_session", _fake_create_session)
    monkeypatch.setattr(app._session_manager, "send_input", lambda _sid, _text: None)
    monkeypatch.setattr(app._session_manager, "resize_session", lambda _sid, _rows, _cols: None)
    monkeypatch.setattr(app, "_list_existing_tmux_sessions", lambda: [])
    return app


async def _create_session_via_dialog(pilot) -> None:
    """Press F2 to open the name dialog, then Enter to accept the default."""
    await pilot.press("f2")
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()


@pytest.mark.asyncio
async def test_app_composes_all_widgets(app: LAMApp) -> None:
    """Verify all major widgets are present after mount."""
    async with app.run_test() as pilot:
        assert app.query_one(HeaderBar)
        assert app.query_one(SessionSidebar)
        assert app.query_one(SessionViewer)
        assert app.query_one(StatusBar)
        assert app.query_one(ToastOverlay)


@pytest.mark.asyncio
async def test_status_bar_initial_text(app: LAMApp) -> None:
    """Status bar should show zero sessions on launch."""
    async with app.run_test() as pilot:
        bar = app.query_one(StatusBar)
        text = str(bar.render())
        assert "Sessions: 0" in text


@pytest.mark.asyncio
async def test_header_bar_initial_text(app: LAMApp) -> None:
    """Header bar should show just 'LAM' on launch with no session selected."""
    async with app.run_test() as pilot:
        header = app.query_one(HeaderBar)
        text = str(header.render())
        assert "LAM" in text


@pytest.mark.asyncio
async def test_new_session_creates_sidebar_item(app: LAMApp) -> None:
    """Pressing F2 + Enter should create a session and add it to the sidebar."""
    async with app.run_test() as pilot:
        await _create_session_via_dialog(pilot)
        items = app.query(SessionListItem)
        assert len(items) == 1
        bar = app.query_one(StatusBar)
        text = str(bar.render())
        assert "Sessions: 1" in text


@pytest.mark.asyncio
async def test_toggle_sidebar(app: LAMApp) -> None:
    """F6 should toggle sidebar visibility."""
    async with app.run_test() as pilot:
        sidebar = app.query_one(SessionSidebar)
        assert sidebar.display is True
        await pilot.press("f6")
        await pilot.pause()
        assert sidebar.display is False
        await pilot.press("f6")
        await pilot.pause()
        assert sidebar.display is True


@pytest.mark.asyncio
async def test_session_receives_pty_output(app: LAMApp) -> None:
    """Creating a session should produce PTY output (shell prompt) in the viewer."""
    async with app.run_test(size=(120, 40)) as pilot:
        await _create_session_via_dialog(pilot)
        for _ in range(20):
            await pilot.pause(delay=0.1)
        viewer = app.query_one(SessionViewer)
        assert "ready" in str(viewer.render())


@pytest.mark.asyncio
async def test_terminal_key_input_does_not_crash(app: LAMApp) -> None:
    """Typing text and pressing Enter in SessionViewer should not crash."""
    async with app.run_test(size=(120, 40)) as pilot:
        await _create_session_via_dialog(pilot)
        viewer = app.query_one(SessionViewer)
        viewer.focus()
        await pilot.pause()
        await pilot.press("e", "c", "h", "o", "space", "h", "e", "l", "l", "o", "enter")
        for _ in range(10):
            await pilot.pause(delay=0.1)


@pytest.mark.asyncio
async def test_navigation_keys_do_not_crash(app: LAMApp) -> None:
    """Arrow keys and Tab should be accepted and forwarded to PTY."""
    async with app.run_test(size=(120, 40)) as pilot:
        await _create_session_via_dialog(pilot)
        viewer = app.query_one(SessionViewer)
        viewer.focus()
        await pilot.press("up")
        await pilot.press("down")
        await pilot.press("tab")
        await pilot.press("enter")
        for _ in range(5):
            await pilot.pause(delay=0.1)
        assert viewer.has_focus


@pytest.mark.asyncio
async def test_header_updates_on_session_create(app: LAMApp) -> None:
    """Header bar should show session info after creating a session."""
    async with app.run_test(size=(120, 40)) as pilot:
        await _create_session_via_dialog(pilot)
        header = app.query_one(HeaderBar)
        text = str(header.render())
        assert "session-1" in text


@pytest.mark.asyncio
async def test_viewer_auto_focused_on_session_select(app: LAMApp) -> None:
    """SessionViewer should receive focus when a session is selected."""
    async with app.run_test(size=(120, 40)) as pilot:
        await _create_session_via_dialog(pilot)
        viewer = app.query_one(SessionViewer)
        assert viewer.has_focus


@pytest.mark.asyncio
async def test_shift_tab_focuses_search(app: LAMApp) -> None:
    async with app.run_test(size=(120, 40)) as pilot:
        await _create_session_via_dialog(pilot)
        viewer = app.query_one(SessionViewer)
        assert viewer.has_focus
        await pilot.press("shift+tab")
        await pilot.pause()
        search = app.query_one("#session-search", Input)
        assert search.has_focus


@pytest.mark.asyncio
async def test_tab_from_search_returns_to_terminal(app: LAMApp) -> None:
    async with app.run_test(size=(120, 40)) as pilot:
        await _create_session_via_dialog(pilot)
        await pilot.press("shift+tab")
        await pilot.pause()
        search = app.query_one("#session-search", Input)
        assert search.has_focus
        await pilot.press("tab")
        await pilot.pause()
        viewer = app.query_one(SessionViewer)
        assert viewer.has_focus


@pytest.mark.asyncio
async def test_click_sidebar_item_switches_session(app: LAMApp) -> None:
    async with app.run_test(size=(120, 40)) as pilot:
        app._create_session("first")
        await pilot.pause()
        app._create_session("second")
        await pilot.pause()
        sessions = app._session_manager.list_sessions()
        first_id = sessions[0].id
        second_id = sessions[1].id
        assert app._active_session_id == second_id
        clicked = await pilot.click(f"#session-item-{first_id}")
        assert clicked is True
        await pilot.pause()
        assert app._active_session_id == first_id
        header = app.query_one(HeaderBar)
        assert "first" in str(header.render())


@pytest.mark.asyncio
async def test_name_dialog_custom_name(app: LAMApp) -> None:
    """Typing a custom name in the dialog should use that name."""
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("f2")
        await pilot.pause()
        # Clear the default name and type a custom one
        await pilot.press("ctrl+a", "backspace")
        for ch in "my-agent":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        header = app.query_one(HeaderBar)
        text = str(header.render())
        assert "my-agent" in text


@pytest.mark.asyncio
async def test_name_dialog_escape_cancels(app: LAMApp) -> None:
    """Pressing Escape in the name dialog should not create a session."""
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("f2")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        items = app.query(SessionListItem)
        assert len(items) == 0


@pytest.mark.asyncio
async def test_empty_state_message(app: LAMApp) -> None:
    """Viewer should show a welcome message when no session is active."""
    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.query_one(SessionViewer)
        text = str(viewer.render())
        assert "No active session" in text
        assert "F2" in text


def test_key_to_pty_mapping(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    app = LAMApp()
    assert app._key_to_pty_input(events.Key("tab", None)) == "\t"
    assert app._key_to_pty_input(events.Key("up", None)) == "\x1b[A"
    assert app._key_to_pty_input(events.Key("ctrl+c", None)) == "\x03"
    assert app._key_to_pty_input(events.Key("a", "a")) == "a"


def test_normalize_legacy_rate_limit_pattern(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    app = LAMApp()
    patterns = app._normalize_error_patterns(
        [r"(?i)\berror\b[:\s]", r"(?i)rate.?limit"]
    )
    assert r"(?i)rate.?limit" not in patterns
    assert (
        r"(?i)rate.?limit(?:ed|ing)?(?:\s+(?:exceeded|reached|hit)|\s*[:\-])"
        in patterns
    )


def test_normalize_legacy_prompt_patterns(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    app = LAMApp()
    patterns = app._normalize_prompt_patterns([r"\[y/n\]"])
    assert r"\?\s*$" in patterns
    assert r"Do you want to (?:continue|proceed)" in patterns
