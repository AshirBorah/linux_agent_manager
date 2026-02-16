from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input

from tame.config.manager import ConfigManager
from tame.notifications.engine import NotificationEngine
from tame.notifications.models import EventType
from tame.session.manager import SessionManager
from tame.session.state import SessionState
from tame.ui.events import (
    SessionOutput,
    SessionSelected,
    SessionStatusChanged,
    SidebarFlash,
)
from tame.ui.keys.manager import KeybindManager
from tame.ui.themes.manager import ThemeManager
from tame.ui.widgets import (
    CommandPalette,
    ConfirmDialog,
    HeaderBar,
    NameDialog,
    SessionSidebar,
    SessionViewer,
    StatusBar,
    ToastOverlay,
)
from tame.utils.logger import setup_logging

log = logging.getLogger("tame.app")

EVENT_TYPE_FOR_STATE: dict[SessionState, EventType] = {
    SessionState.WAITING: EventType.INPUT_NEEDED,
    SessionState.ERROR: EventType.ERROR,
    SessionState.DONE: EventType.COMPLETED,
    SessionState.IDLE: EventType.SESSION_IDLE,
}

BROAD_RATE_LIMIT_PATTERNS = {
    r"(?i)rate.?limit",
    r"rate.?limit",
}
REFINED_RATE_LIMIT_PATTERN = (
    r"(?i)rate.?limit(?:ed|ing)?(?:\s+(?:exceeded|reached|hit)|\s*[:\-])"
)
REQUIRED_PROMPT_PATTERNS = [
    r"Do you want to (?:continue|proceed)",
    r"\?\s*$",
]

SPECIAL_KEY_SEQUENCES: dict[str, str] = {
    "enter": "\r",
    "return": "\r",
    "tab": "\t",
    "shift+tab": "\x1b[Z",
    "escape": "\x1b",
    "backspace": "\x7f",
    "delete": "\x1b[3~",
    "insert": "\x1b[2~",
    "up": "\x1b[A",
    "down": "\x1b[B",
    "right": "\x1b[C",
    "left": "\x1b[D",
    "home": "\x1b[H",
    "end": "\x1b[F",
    "pageup": "\x1b[5~",
    "pagedown": "\x1b[6~",
}

CTRL_SPECIAL_SEQUENCES: dict[str, str] = {
    "space": "\x00",
    "at": "\x00",
    "left_square_bracket": "\x1b",
    "backslash": "\x1c",
    "right_square_bracket": "\x1d",
    "circumflex_accent": "\x1e",
    "underscore": "\x1f",
}


class TAMEApp(App):
    CSS = """
    Screen {
        background: #1e1e1e;
        color: #d4d4d4;
    }

    #main-content {
        height: 1fr;
        width: 1fr;
    }

    #right-panel {
        height: 1fr;
        width: 1fr;
    }

    #session-viewer {
        width: 1fr;
        height: 1fr;
    }
    """

    COMMAND_MODE_MAP: dict[str, str] = {
        "c": "new_session",
        "n": "next_session",
        "p": "prev_session",
        "k": "kill_session",
        "s": "toggle_sidebar",
        "r": "resume_all",
        "z": "pause_all",
        "x": "clear_notifications",
        "q": "quit",
    }

    BINDINGS = [
        Binding("f2", "new_session", "New Session", show=True),
        Binding("f3", "prev_session", "Prev Session", show=True),
        Binding("f4", "next_session", "Next Session", show=True),
        Binding("f6", "toggle_sidebar", "Toggle Sidebar", show=True),
        Binding("f7", "resume_all", "Resume All", show=False),
        Binding("f8", "pause_all", "Pause All", show=False),
        Binding("f12", "quit", "Quit", show=True),
        Binding("tab", "send_tab", "Tab Complete", show=False, priority=True),
        Binding(
            "shift+tab",
            "focus_search",
            "Focus Search",
            show=False,
            priority=True,
        ),
    ]

    def __init__(
        self,
        config_path: str | None = None,
        theme_override: str | None = None,
        verbose: bool = False,
    ) -> None:
        self._config_manager = ConfigManager(config_path)
        cfg = self._config_manager.config

        self._theme_manager = ThemeManager(
            current=theme_override or str(cfg.get("theme", {}).get("current", "dark")),
            custom_css_path=str(cfg.get("theme", {}).get("custom_css_path", "")),
        )
        css_path = self._theme_manager.get_css_path()

        super().__init__(css_path=str(css_path) if css_path else None)

        log_level = "DEBUG" if verbose else str(cfg.get("general", {}).get("log_level", "INFO"))
        log_file = str(cfg.get("general", {}).get("log_file", ""))
        setup_logging(log_file=log_file, log_level=log_level)

        self._keybind_manager = KeybindManager(cfg.get("keybindings"))
        self._reserved_keys = {binding.key for binding in self.BINDINGS}
        self._reserved_keys.add("ctrl+@")
        self._reserved_keys.add("ctrl+space")

        self._session_manager = SessionManager(
            on_status_change=self._handle_status_change,
            on_output=self._handle_pty_output,
            patterns=self._get_patterns_from_config(cfg),
        )
        sessions_cfg = cfg.get("sessions", {})
        default_working_dir = str(sessions_cfg.get("default_working_directory", "")).strip()
        self._default_working_dir = os.path.expanduser(default_working_dir) if default_working_dir else os.path.expanduser("~")
        default_shell = str(sessions_cfg.get("default_shell", "")).strip()
        self._default_shell = default_shell or os.environ.get("SHELL", "/bin/bash")

        self._start_in_tmux = bool(sessions_cfg.get("start_in_tmux", False))
        self._restore_tmux_sessions_on_startup = bool(
            sessions_cfg.get("restore_tmux_sessions_on_startup", True)
        )
        tmux_prefix = str(sessions_cfg.get("tmux_session_prefix", "tame")).strip()
        self._tmux_session_prefix = tmux_prefix or "tame"
        self._tmux_available = shutil.which("tmux") is not None
        if self._start_in_tmux and not self._tmux_available:
            log.warning("sessions.start_in_tmux=true but tmux is not installed; falling back to shell")

        notif_cfg = cfg.get("notifications", {})
        self._notification_engine = NotificationEngine(notif_cfg)
        self._notification_engine.on_toast = self._handle_notification_toast
        self._notification_engine.on_sidebar_flash = self._handle_sidebar_flash

        self._active_session_id: str | None = None

    def _get_patterns_from_config(self, cfg: dict) -> dict[str, list[str]] | None:
        patterns_cfg = cfg.get("patterns", {})
        if not patterns_cfg:
            return None
        result: dict[str, list[str]] = {}
        for category in ("error", "prompt", "completion", "progress"):
            cat_cfg = patterns_cfg.get(category, {})
            if isinstance(cat_cfg, dict) and ("regexes" in cat_cfg or "shell_regexes" in cat_cfg):
                regexes = list(cat_cfg.get("regexes", []))
                shell_regexes = list(cat_cfg.get("shell_regexes", []))
                if category == "error":
                    regexes = self._normalize_error_patterns(regexes)
                elif category == "prompt":
                    regexes = self._normalize_prompt_patterns(regexes)
                result[category] = regexes + shell_regexes
        return result or None

    def _normalize_error_patterns(self, regexes: list[str]) -> list[str]:
        """Normalize known-bad legacy patterns for backward compatibility."""
        normalized: list[str] = []
        saw_rate_limit = False
        for pattern in regexes:
            if pattern in BROAD_RATE_LIMIT_PATTERNS:
                saw_rate_limit = True
                continue
            normalized.append(pattern)
            if pattern == REFINED_RATE_LIMIT_PATTERN:
                saw_rate_limit = True
        if saw_rate_limit:
            normalized.append(REFINED_RATE_LIMIT_PATTERN)
        return normalized

    def _normalize_prompt_patterns(self, regexes: list[str]) -> list[str]:
        """Ensure baseline prompt detection patterns exist in user config."""
        normalized = list(regexes)
        for required in REQUIRED_PROMPT_PATTERNS:
            if required not in normalized:
                normalized.append(required)
        return normalized

    def compose(self) -> ComposeResult:
        yield HeaderBar()
        with Horizontal(id="main-content"):
            yield SessionSidebar()
            with Vertical(id="right-panel"):
                yield SessionViewer()
        yield StatusBar()
        yield ToastOverlay()

    def on_mount(self) -> None:
        loop = asyncio.get_running_loop()
        self._session_manager.attach_to_loop(loop)
        self.call_later(self._restore_tmux_sessions_async)
        log.info("TAME started")

    # ------------------------------------------------------------------
    # Session status change callback (from SessionManager, may be called
    # from a non-main thread via PTY reader)
    # ------------------------------------------------------------------

    def _handle_status_change(
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

    def _handle_notification_toast(self, event) -> None:
        try:
            toast = self.query_one(ToastOverlay)
            toast.show_toast(
                title=f"TAME [{event.event_type.value}]",
                message=f"{event.session_name}: {event.message}",
            )
        except Exception:
            pass

    def _handle_sidebar_flash(self, event) -> None:
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
        if event.session_id == self._active_session_id:
            header = self.query_one(HeaderBar)
            header.update_from_session(session)
        self._update_status_bar()

    def on_sidebar_flash(self, event: SidebarFlash) -> None:
        try:
            from tame.ui.widgets.session_list_item import SessionListItem
            item = self.query_one(f"#session-item-{event.session_id}", SessionListItem)
            item.add_class("flash")
            self.set_timer(2.0, lambda: item.remove_class("flash"))
        except Exception:
            pass

    def on_session_selected(self, event: SessionSelected) -> None:
        self._select_session(event.session_id)

    def on_button_pressed(self, event) -> None:
        if event.button.id == "new-session-btn":
            self.action_new_session()

    def on_resize(self, event: events.Resize) -> None:
        del event
        self._resize_active_session()

    def on_key(self, event: events.Key) -> None:
        # --- Open command palette overlay ---
        if event.key in ("ctrl+@", "ctrl+space"):
            if not isinstance(self.screen, (NameDialog, ConfirmDialog, CommandPalette)):
                self.push_screen(CommandPalette(), callback=self._handle_command_result)
            event.stop()
            return

        # --- Normal key forwarding ---
        if not self._should_forward_key(event):
            return

        pty_input = self._key_to_pty_input(event)
        if pty_input is None or self._active_session_id is None:
            return

        self._session_manager.send_input(self._active_session_id, pty_input)
        event.stop()

    # ------------------------------------------------------------------
    # Command palette callback
    # ------------------------------------------------------------------

    def _handle_command_result(self, action_name: str | None) -> None:
        if action_name is None:
            return
        method = getattr(self, f"action_{action_name}", None)
        if method is None:
            return
        if asyncio.iscoroutinefunction(method):
            self.call_later(method)
        else:
            method()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_clear_notifications(self) -> None:
        """Dismiss the current toast and clear all sidebar flashes."""
        try:
            self.query_one(ToastOverlay).dismiss_now()
        except Exception:
            pass
        try:
            self.query_one(SessionSidebar).clear_all_flash()
        except Exception:
            pass

    def action_new_session(self) -> None:
        default_name = f"session-{len(self._session_manager.list_sessions()) + 1}"
        self.push_screen(NameDialog(default_name), callback=self._create_session)

    def _create_session(self, name: str | None) -> None:
        if name is None:
            return

        working_dir = self._default_working_dir
        if not os.path.isdir(working_dir):
            working_dir = os.path.expanduser("~")

        command = self._build_session_command(name)
        session = self._session_manager.create_session(
            name,
            working_dir,
            shell=self._default_shell,
            command=command,
        )
        tmux_session_name = self._build_tmux_session_name(name)
        if command and tmux_session_name:
            session.metadata["tmux_session_name"] = tmux_session_name

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

    def action_kill_session(self) -> None:
        if isinstance(self.screen, (NameDialog, ConfirmDialog, CommandPalette)):
            return
        if self._active_session_id is None:
            return
        try:
            session = self._session_manager.get_session(self._active_session_id)
        except KeyError:
            return
        self.push_screen(
            ConfirmDialog(f"Kill session '{session.name}'?"),
            callback=self._confirm_kill_session,
        )

    def _confirm_kill_session(self, confirmed: bool) -> None:
        if not confirmed:
            return
        session_id = self._active_session_id
        if session_id is None:
            return

        sidebar = self.query_one(SessionSidebar)
        viewer = self.query_one(SessionViewer)

        sidebar.remove_session(session_id)
        viewer.remove_session(session_id)

        try:
            self._session_manager.delete_session(session_id)
        except KeyError:
            pass

        # Switch to the next available session or clear
        sessions = self._session_manager.list_sessions()
        if sessions:
            self._select_session(sessions[0].id)
        else:
            self._active_session_id = None
            header = self.query_one(HeaderBar)
            header.clear_session()

        self._update_status_bar()
        log.info("Killed session %s", session_id)

    def action_send_tab(self) -> None:
        if isinstance(self.screen, (NameDialog, ConfirmDialog, CommandPalette)):
            return
        if self._active_session_id is None:
            return
        self._session_manager.send_input(self._active_session_id, "\t")
        try:
            self.query_one(SessionViewer).focus()
        except Exception:
            pass

    def action_focus_search(self) -> None:
        if isinstance(self.screen, (NameDialog, ConfirmDialog, CommandPalette)):
            return
        sidebar = self.query_one(SessionSidebar)
        search_input = sidebar.query_one("#session-search", Input)
        search_input.focus()

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

        header = self.query_one(HeaderBar)
        header.update_from_session(session)

        viewer = self.query_one(SessionViewer)
        viewer.load_session(session_id, session.output_buffer)
        viewer.focus()
        self._resize_active_session()

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

    def _handle_pty_output(self, session_id: str, text: str) -> None:
        self.post_message(SessionOutput(session_id, text))

    def on_session_output(self, event: SessionOutput) -> None:
        viewer = self.query_one(SessionViewer)
        if event.session_id == self._active_session_id:
            viewer.append_output(event.data)
        else:
            viewer.feed_session(event.session_id, event.data)

    # ------------------------------------------------------------------
    # Terminal input + resize helpers
    # ------------------------------------------------------------------

    async def _restore_tmux_sessions_async(self) -> None:
        """Non-blocking tmux session restore — runs subprocess calls in executor."""
        if not (
            self._start_in_tmux
            and self._tmux_available
            and self._restore_tmux_sessions_on_startup
        ):
            return

        loop = asyncio.get_running_loop()
        tmux_sessions = await loop.run_in_executor(
            None, self._list_existing_tmux_sessions
        )
        if not tmux_sessions:
            return

        working_dir = self._default_working_dir
        if not os.path.isdir(working_dir):
            working_dir = os.path.expanduser("~")

        sidebar = self.query_one(SessionSidebar)
        restored_count = 0
        for tmux_session in tmux_sessions:
            display_name = self._display_name_for_tmux_session(tmux_session)
            try:
                session = self._session_manager.create_session(
                    display_name,
                    working_dir,
                    shell=self._default_shell,
                    command=["tmux", "attach-session", "-t", tmux_session],
                )
            except Exception:
                log.exception("Failed to restore tmux session '%s'", tmux_session)
                continue

            session.metadata["tmux_session_name"] = tmux_session

            pane_text = await loop.run_in_executor(
                None, self._capture_tmux_pane, tmux_session
            )
            if pane_text:
                self._session_manager.scan_pane_content(session.id, pane_text)

            sidebar.add_session(session)
            if self._active_session_id is None:
                self._select_session(session.id)
            restored_count += 1

        if restored_count:
            self._update_status_bar()
            log.info("Restored %d tmux session(s)", restored_count)

    def _restore_tmux_sessions(self) -> None:
        """Synchronous tmux session restore (used by tests)."""
        if not (
            self._start_in_tmux
            and self._tmux_available
            and self._restore_tmux_sessions_on_startup
        ):
            return

        tmux_sessions = self._list_existing_tmux_sessions()
        if not tmux_sessions:
            return

        working_dir = self._default_working_dir
        if not os.path.isdir(working_dir):
            working_dir = os.path.expanduser("~")

        sidebar = self.query_one(SessionSidebar)
        restored_count = 0
        for tmux_session in tmux_sessions:
            display_name = self._display_name_for_tmux_session(tmux_session)
            try:
                session = self._session_manager.create_session(
                    display_name,
                    working_dir,
                    shell=self._default_shell,
                    command=["tmux", "attach-session", "-t", tmux_session],
                )
            except Exception:
                log.exception("Failed to restore tmux session '%s'", tmux_session)
                continue

            session.metadata["tmux_session_name"] = tmux_session

            pane_text = self._capture_tmux_pane(tmux_session)
            if pane_text:
                self._session_manager.scan_pane_content(session.id, pane_text)

            sidebar.add_session(session)
            if self._active_session_id is None:
                self._select_session(session.id)
            restored_count += 1

        if restored_count:
            self._update_status_bar()
            log.info("Restored %d tmux session(s)", restored_count)

    def _capture_tmux_pane(self, tmux_session: str) -> str:
        proc = subprocess.run(
            ["tmux", "capture-pane", "-p", "-t", tmux_session],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return ""
        return proc.stdout

    def _list_existing_tmux_sessions(self) -> list[str]:
        proc = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip().lower()
            if "no server running" in stderr or "failed to connect" in stderr:
                return []
            log.warning("Unable to list tmux sessions: %s", proc.stderr.strip())
            return []

        prefix = f"{self._tmux_session_prefix}-"
        sessions: list[str] = []
        for line in proc.stdout.splitlines():
            name = line.strip()
            if not name:
                continue
            if name.startswith(prefix):
                sessions.append(name)
        sessions.sort()
        return sessions

    def _build_session_command(self, session_name: str) -> list[str] | None:
        tmux_session = self._build_tmux_session_name(session_name)
        if tmux_session is None:
            return None
        return ["tmux", "new-session", "-A", "-s", tmux_session]

    def _build_tmux_session_name(self, session_name: str) -> str | None:
        if not (self._start_in_tmux and self._tmux_available):
            return None
        safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", session_name).strip("_")
        if not safe_name:
            safe_name = "session"
        return f"{self._tmux_session_prefix}-{safe_name}"

    def _display_name_for_tmux_session(self, tmux_session: str) -> str:
        prefix = f"{self._tmux_session_prefix}-"
        if tmux_session.startswith(prefix):
            return tmux_session[len(prefix):]
        return tmux_session

    def _resize_active_session(self) -> None:
        if self._active_session_id is None:
            return
        try:
            viewer = self.query_one(SessionViewer)
            rows = max(1, viewer.size.height)
            cols = max(1, viewer.size.width)
            self._session_manager.resize_session(self._active_session_id, rows, cols)
        except Exception:
            pass

    def _should_forward_key(self, event: events.Key) -> bool:
        if self._active_session_id is None:
            return False
        if any(alias in self._reserved_keys for alias in event.aliases):
            return False
        focused = self.focused
        if isinstance(focused, Input):
            return False
        return True

    def _key_to_pty_input(self, event: events.Key) -> str | None:
        key = event.key
        if key in SPECIAL_KEY_SEQUENCES:
            return SPECIAL_KEY_SEQUENCES[key]

        if key.startswith("ctrl+"):
            ctrl_key = key[5:]
            if len(ctrl_key) == 1 and ctrl_key.isalpha():
                return chr(ord(ctrl_key.lower()) - ord("a") + 1)
            return CTRL_SPECIAL_SEQUENCES.get(ctrl_key)

        if key.startswith("alt+"):
            alt_key = key[4:]
            if len(alt_key) == 1:
                return f"\x1b{alt_key}"

        if event.character is not None:
            return event.character
        return None

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def on_unmount(self) -> None:
        self._session_manager.close_all()
