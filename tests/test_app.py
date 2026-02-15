"""Smoke tests for the LAMApp TUI using Textual's async pilot."""
from __future__ import annotations

import pytest

from lam.app import LAMApp
from lam.ui.widgets import (
    HeaderBar,
    InputArea,
    SessionHeader,
    SessionSidebar,
    SessionViewer,
    StatusBar,
    ToastOverlay,
)
from lam.ui.widgets.session_list_item import SessionListItem


@pytest.fixture
def app() -> LAMApp:
    return LAMApp()


@pytest.mark.asyncio
async def test_app_composes_all_widgets(app: LAMApp) -> None:
    """Verify all major widgets are present after mount."""
    async with app.run_test() as pilot:
        assert app.query_one(HeaderBar)
        assert app.query_one(SessionSidebar)
        assert app.query_one(SessionHeader)
        assert app.query_one(SessionViewer)
        assert app.query_one(InputArea)
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
async def test_session_header_initial_text(app: LAMApp) -> None:
    """Session header should show placeholder text on launch."""
    async with app.run_test() as pilot:
        header = app.query_one(SessionHeader)
        text = str(header.render())
        assert "No session selected" in text


@pytest.mark.asyncio
async def test_new_session_creates_sidebar_item(app: LAMApp) -> None:
    """Pressing Ctrl+N should create a session and add it to the sidebar."""
    async with app.run_test() as pilot:
        await pilot.press("ctrl+n")
        await pilot.pause()
        items = app.query(SessionListItem)
        assert len(items) == 1
        bar = app.query_one(StatusBar)
        text = str(bar.render())
        assert "Sessions: 1" in text


@pytest.mark.asyncio
async def test_toggle_sidebar(app: LAMApp) -> None:
    """Ctrl+B should toggle sidebar visibility."""
    async with app.run_test() as pilot:
        sidebar = app.query_one(SessionSidebar)
        assert sidebar.display is True
        await pilot.press("ctrl+b")
        await pilot.pause()
        assert sidebar.display is False
        await pilot.press("ctrl+b")
        await pilot.pause()
        assert sidebar.display is True
