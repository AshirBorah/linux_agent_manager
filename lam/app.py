from __future__ import annotations

import asyncio
import logging
import os

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button

from lam.config.manager import ConfigManager
from lam.notifications.engine import NotificationEngine
from lam.notifications.models import EventType
from lam.session.manager import SessionManager
from lam.session.state import SessionState
from lam.ui.events import (
    InputSubmitted,
    SessionOutput,
    SessionSelected,
    SessionStatusChanged,
    SidebarFlash,
)
from lam.ui.keys.manager import KeybindManager
from lam.ui.themes.manager import ThemeManager
from lam.ui.widgets import (
    HeaderBar,
    InputArea,
    SessionHeader,
    SessionSidebar,
    SessionViewer,
    StatusBar,
    ToastOverlay,
)
from lam.utils.logger import setup_logging

log = logging.getLogger("lam.app")

EVENT_TYPE_FOR_STATE: dict[SessionState, EventType] = {
    SessionState.WAITING: EventType.INPUT_NEEDED,
    SessionState.ERROR: EventType.ERROR,
    SessionState.DONE: EventType.COMPLETED,
    SessionState.IDLE: EventType.SESSION_IDLE,
}


class LAMApp(App):
    CSS = """
    Screen {
        background: #1e1e1e;
        color: #d4d4d4;
    }

    #main-content {
        height: 1fr;
    }

    #right-panel {
        height: 100%;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+n", "new_session", "New Session", show=True),
        Binding("ctrl+b", "toggle_sidebar", "Toggle Sidebar", show=False),
        Binding("ctrl+up", "prev_session", "Prev Session", show=False),
        Binding("ctrl+down", "next_session", "Next Session", show=False),
        Binding("ctrl+r", "resume_all", "Resume All", show=False),
        Binding("ctrl+p", "pause_all", "Pause All", show=False),
    ]

    def __init__(
        self,
        config_path: str | None = None,
        theme_override: str | None = None,
        verbose: bool = False,
    ) -> None:
        super().__init__()
        self._config_manager = ConfigManager(config_path)
        cfg = self._config_manager.config

        log_level = "DEBUG" if verbose else str(cfg.get("general", {}).get("log_level", "INFO"))
        log_file = str(cfg.get("general", {}).get("log_file", ""))
        setup_logging(log_file=log_file, log_level=log_level)

        self._theme_manager = ThemeManager(
            current=theme_override or str(cfg.get("theme", {}).get("current", "dark")),
        )
        self._keybind_manager = KeybindManager(cfg.get("keybindings"))

        self._session_manager = SessionManager(
            on_status_change=self._on_session_status_change,
            on_output=self._on_session_output,
            patterns=self._get_patterns_from_config(cfg),
        )

        notif_cfg = cfg.get("notifications", {})
        self._notification_engine = NotificationEngine(notif_cfg)
        self._notification_engine.on_toast = self._on_notification_toast
        self._notification_engine.on_sidebar_flash = self._on_sidebar_flash

        self._active_session_id: str | None = None

    def _get_patterns_from_config(self, cfg: dict) -> dict[str, list[str]] | None:
        patterns_cfg = cfg.get("patterns", {})
        if not patterns_cfg:
            return None
        result: dict[str, list[str]] = {}
        for category in ("error", "prompt", "completion", "progress"):
            cat_cfg = patterns_cfg.get(category, {})
            if isinstance(cat_cfg, dict) and "regexes" in cat_cfg:
                result[category] = cat_cfg["regexes"]
        return result or None

    def compose(self) -> ComposeResult:
        yield HeaderBar()
        with Horizontal(id="main-content"):
            yield SessionSidebar()
            with Vertical(id="right-panel"):
                yield SessionHeader()
                yield SessionViewer()
                yield InputArea()
        yield StatusBar()
        yield ToastOverlay()

    def on_mount(self) -> None:
        loop = asyncio.get_running_loop()
        self._session_manager.attach_to_loop(loop)
        log.info("LAM started")

    # ------------------------------------------------------------------
    # Session status change callback (from SessionManager, may be called
    # from a non-main thread via PTY reader)
    # ------------------------------------------------------------------

    def _on_session_status_change(
        self, session_id: str, old_state: SessionState, new_state: SessionState
    ) -> None:
        self.post_message(
            SessionStatusChanged(session_id, old_state.value, new_state.value)
        )
        event_type = EVENT_TYPE_FOR_STATE.get(new_state)
        if event_type:
            session = self._session_manager.get_session(session_id)
            self._notification_engine.dispatch(
                event_type=event_type,
                session_id=session_id,
                session_name=session.name,
                message=f"Session '{session.name}' is now {new_state.value}",
            )

    def _on_notification_toast(self, event) -> None:
        try:
            toast = self.query_one(ToastOverlay)
            toast.show_toast(
                title=f"LAM [{event.event_type.value}]",
                message=f"{event.session_name}: {event.message}",
            )
        except Exception:
            pass

    def _on_sidebar_flash(self, event) -> None:
        self.post_message(SidebarFlash(event.session_id))

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    def on_session_status_changed(self, event: SessionStatusChanged) -> None:
        try:
            session = self._session_manager.get_session(event.session_id)
        except KeyError:
            return
        sidebar = self.query_one(SessionSidebar)
        sidebar.update_session(session)
        self._update_status_bar()

    def on_sidebar_flash(self, event: SidebarFlash) -> None:
        try:
            from lam.ui.widgets.session_list_item import SessionListItem
            item = self.query_one(f"#session-item-{event.session_id}", SessionListItem)
            item.add_class("flash")
            self.set_timer(2.0, lambda: item.remove_class("flash"))
        except Exception:
            pass

    def on_session_selected(self, event: SessionSelected) -> None:
        self._select_session(event.session_id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "new-session-btn":
            self.action_new_session()
        elif event.button.id == "resume-all":
            self.action_resume_all()
        elif event.button.id == "pause-all":
            self.action_pause_all()

    def on_input_submitted(self, event: InputSubmitted) -> None:
        if self._active_session_id:
            self._session_manager.send_input(
                self._active_session_id, event.text + "\n"
            )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_new_session(self) -> None:
        name = f"session-{len(self._session_manager.list_sessions()) + 1}"
        working_dir = os.path.expanduser("~")
        session = self._session_manager.create_session(name, working_dir)

        sidebar = self.query_one(SessionSidebar)
        sidebar.add_session(session)
        self._select_session(session.id)
        self._update_status_bar()
        log.info("Created session %s (%s)", session.name, session.id)

    def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one(SessionSidebar)
        sidebar.display = not sidebar.display

    def action_prev_session(self) -> None:
        self._switch_session_relative(-1)

    def action_next_session(self) -> None:
        self._switch_session_relative(1)

    def action_resume_all(self) -> None:
        self._session_manager.resume_all()

    def action_pause_all(self) -> None:
        self._session_manager.pause_all()

    # ------------------------------------------------------------------
    # Session selection
    # ------------------------------------------------------------------

    def _select_session(self, session_id: str) -> None:
        self._active_session_id = session_id

        sidebar = self.query_one(SessionSidebar)
        sidebar.highlight_session(session_id)

        try:
            session = self._session_manager.get_session(session_id)
        except KeyError:
            return

        header = self.query_one(SessionHeader)
        header.update_from_session(session)

        viewer = self.query_one(SessionViewer)
        viewer.load_buffer(session.output_buffer)

    def _switch_session_relative(self, delta: int) -> None:
        sessions = self._session_manager.list_sessions()
        if not sessions:
            return
        if self._active_session_id is None:
            self._select_session(sessions[0].id)
            return
        ids = [s.id for s in sessions]
        try:
            idx = ids.index(self._active_session_id)
        except ValueError:
            idx = 0
        new_idx = (idx + delta) % len(ids)
        self._select_session(ids[new_idx])

    def _update_status_bar(self) -> None:
        sessions = self._session_manager.list_sessions()
        total = len(sessions)
        active = sum(1 for s in sessions if s.status == SessionState.ACTIVE)
        waiting = sum(1 for s in sessions if s.status == SessionState.WAITING)
        errors = sum(1 for s in sessions if s.status == SessionState.ERROR)
        bar = self.query_one(StatusBar)
        bar.update_stats(total, active, waiting, errors)

    # ------------------------------------------------------------------
    # PTY output -> UI
    # ------------------------------------------------------------------

    def _on_session_output(self, session_id: str, text: str) -> None:
        self.post_message(SessionOutput(session_id, text))

    def on_session_output(self, event: SessionOutput) -> None:
        if event.session_id == self._active_session_id:
            viewer = self.query_one(SessionViewer)
            viewer.append_output(event.data)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def on_unmount(self) -> None:
        self._session_manager.close_all()
