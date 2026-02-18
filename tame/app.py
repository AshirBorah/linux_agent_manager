from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import Input

from tame.config.manager import ConfigManager
from tame.notifications.engine import NotificationEngine
from tame.notifications.models import EventType
from tame.session.manager import SessionManager
from tame.session.state import SessionState
from tame.ui.events import (
    SearchDismissed,
    SearchNavigate,
    SearchQueryChanged,
    SessionSelected,
    SessionStatusChanged,
    SidebarFlash,
    ViewerResized,
)
from tame.ui.keys.manager import KeybindManager
from tame.ui.themes.manager import ThemeManager
from tame.ui.widgets import (
    CommandPalette,
    ConfirmDialog,
    DiffViewer,
    EasterEgg,
    GroupDialog,
    HeaderBar,
    HistoryPicker,
    MemoryClearDialog,
    MemoryEnableDialog,
    MemoryRecallDialog,
    NameDialog,
    NotificationPanel,
    SearchDialog,
    SessionSearchBar,
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
REDRAW_CONTROL_RE = re.compile(r"\x1b\[[0-9;?]*(?:[ABCDHfJK])|\x1bc|\x0c|\r(?!\n)")
SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")

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
        "d": "delete_session",
        "e": "export_session",
        "f": "session_search",
        "g": "global_search",
        "h": "show_history",
        "l": "notification_history",
        "m": "rename_session",
        "n": "next_session",
        "p": "prev_session",
        "1": "session_1",
        "2": "session_2",
        "3": "session_3",
        "4": "session_4",
        "5": "session_5",
        "6": "session_6",
        "7": "session_7",
        "8": "session_8",
        "9": "session_9",
        "s": "toggle_sidebar",
        "i": "focus_input",
        "t": "toggle_theme",
        "r": "resume_all",
        "z": "pause_all",
        "u": "check_usage",
        "x": "clear_notifications",
        "w": "set_group",
        "v": "show_diff",
        "y": "toggle_memory",
        "a": "recall_memory",
        "j": "clear_memory",
        "q": "quit",
    }

    # Configurable keybindings — mapped action → (description, show, priority).
    # The action name must match an action_<name>() method on the class.
    _BINDING_META: dict[str, tuple[str, bool, bool]] = {
        "new_session": ("New Session", True, False),
        "rename_session": ("Rename Session", False, False),
        "prev_session": ("Prev Session", True, False),
        "next_session": ("Next Session", True, False),
        "toggle_sidebar": ("Toggle Sidebar", True, False),
        "resume_all": ("Resume All", False, False),
        "pause_all": ("Pause All", False, False),
        "show_diff": ("Git Diff", False, False),
        "set_group": ("Set Group", False, False),
        "focus_search": ("Focus Search", False, False),
        "quit": ("Quit", True, False),
        "session_1": ("Session 1", False, False),
        "session_2": ("Session 2", False, False),
        "session_3": ("Session 3", False, False),
        "session_4": ("Session 4", False, False),
        "session_5": ("Session 5", False, False),
        "session_6": ("Session 6", False, False),
        "session_7": ("Session 7", False, False),
        "session_8": ("Session 8", False, False),
        "session_9": ("Session 9", False, False),
    }

    # Hardcoded bindings that are not user-configurable.
    BINDINGS = [
        Binding("ctrl+c", "send_sigint", "Send SIGINT", show=False, priority=True),
        Binding("ctrl+d", "send_eof", "Send EOF", show=False, priority=True),
        Binding(
            "ctrl+f", "session_search", "Search in Session", show=False, priority=True
        ),
        Binding(
            "ctrl+shift+f", "global_search", "Global Search", show=False, priority=True
        ),
        Binding(
            "f5", "notification_history", "Notification Log", show=True, priority=False
        ),
        Binding("tab", "send_tab", "Tab Complete", show=False, priority=True),
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

        log_level = (
            "DEBUG" if verbose else str(cfg.get("general", {}).get("log_level", "INFO"))
        )
        log_file = str(cfg.get("general", {}).get("log_file", ""))
        setup_logging(log_file=log_file, log_level=log_level)

        self._keybind_manager = KeybindManager(cfg.get("keybindings"))

        # Wire configurable bindings from KeybindManager
        for action, (desc, show, priority) in self._BINDING_META.items():
            key = self._keybind_manager.get_key(action)
            if key:
                self._bindings.bind(
                    key,
                    action,
                    description=desc,
                    show=show,
                    priority=priority,
                )

        for conflict in self._keybind_manager.conflicts:
            log.warning("Keybinding conflict: %s", conflict)

        self._reserved_keys: set[str] = set(self._bindings.key_to_bindings)
        self._reserved_keys.add("ctrl+@")
        self._reserved_keys.add("ctrl+space")

        sessions_cfg = cfg.get("sessions", {})
        idle_threshold = float(sessions_cfg.get("idle_threshold_seconds", 300))
        patterns_cfg = cfg.get("patterns", {})
        idle_prompt_timeout = float(patterns_cfg.get("idle_prompt_timeout", 3.0))
        state_debounce_ms = float(patterns_cfg.get("state_debounce_ms", 500))
        self._session_manager = SessionManager(
            on_status_change=self._handle_status_change,
            on_output=self._handle_pty_output,
            patterns=self._get_patterns_from_config(cfg),
            idle_threshold_seconds=idle_threshold,
            idle_prompt_timeout=idle_prompt_timeout,
            state_debounce_ms=state_debounce_ms,
        )
        default_working_dir = str(
            sessions_cfg.get("default_working_directory", "")
        ).strip()
        self._default_working_dir = (
            os.path.expanduser(default_working_dir)
            if default_working_dir
            else os.path.expanduser("~")
        )
        default_shell = str(sessions_cfg.get("default_shell", "")).strip()
        self._default_shell = default_shell or os.environ.get("SHELL", "/bin/bash")

        self._start_in_tmux = bool(sessions_cfg.get("start_in_tmux", False))
        self._restore_tmux_sessions_on_startup = bool(
            sessions_cfg.get("restore_tmux_sessions_on_startup", True)
        )
        self._tmux_snapshot_render = bool(
            sessions_cfg.get("tmux_snapshot_render", self._start_in_tmux)
        )
        tmux_prefix = str(sessions_cfg.get("tmux_session_prefix", "tame")).strip()
        self._tmux_session_prefix = tmux_prefix or "tame"
        self._tmux_available = shutil.which("tmux") is not None
        if self._start_in_tmux and not self._tmux_available:
            log.warning(
                "sessions.start_in_tmux=true but tmux is not installed; falling back to shell"
            )

        notif_cfg = cfg.get("notifications", {})
        self._notification_engine = NotificationEngine(notif_cfg)
        self._notification_engine.on_toast = self._handle_notification_toast
        self._notification_engine.on_sidebar_flash = self._handle_sidebar_flash

        git_cfg = cfg.get("git", {})
        self._worktrees_enabled = bool(git_cfg.get("worktrees_enabled", False))
        git_repo_dir = str(git_cfg.get("repo_dir", "")).strip()
        self._git_repo_dir = (
            os.path.expanduser(git_repo_dir)
            if git_repo_dir
            else self._default_working_dir
        )

        # Letta memory integration (optional)
        self._memory_bridge = self._init_memory_bridge(cfg)
        self._memory_ever_enabled = bool(cfg.get("letta", {}).get("enabled", False))

        self._active_session_id: str | None = None
        self._pending_status_updates: set[str] = set()
        self._status_update_scheduled: bool = False

        # Batched PTY output: accumulate chunks per session, flush on timer
        self._output_pending: dict[str, list[str]] = {}
        self._output_flush_timer: Timer | None = None
        self._app_focused: bool = True

        # Input history: accumulate typed chars per session, flush on Enter
        self._input_line_buffer: dict[str, list[str]] = {}

        # Easter egg: triggers once per app run
        self._easter_egg_shown: bool = False

    @staticmethod
    def _letta_available() -> bool:
        """Check if the letta-client package is installed."""
        try:
            import letta_client  # noqa: F401

            return True
        except ImportError:
            return False

    def _init_memory_bridge(self, cfg: dict):  # noqa: ANN201
        """Conditionally create the memory bridge if letta-client is installed."""
        if not self._letta_available():
            return None
        from tame.integrations.letta import MemoryBridge

        letta_cfg = cfg.get("letta", {})
        server_url = str(letta_cfg.get("server_url", "http://localhost:8283"))
        bridge = MemoryBridge(server_url)
        if letta_cfg.get("enabled", False):
            ok, msg = bridge.enable()
            if ok:
                log.info("Letta memory bridge enabled: %s", msg)
            else:
                log.warning("Letta memory bridge failed to connect: %s", msg)
        return bridge

    def _get_patterns_from_config(self, cfg: dict) -> dict[str, list[str]]:
        patterns_cfg = cfg.get("patterns", {})
        if not patterns_cfg:
            return {}
        result: dict[str, list[str]] = {}
        for category in ("error", "prompt", "completion", "progress"):
            cat_cfg = patterns_cfg.get(category, {})
            if isinstance(cat_cfg, dict) and (
                "regexes" in cat_cfg or "shell_regexes" in cat_cfg
            ):
                regexes = list(cat_cfg.get("regexes", []))
                shell_regexes = list(cat_cfg.get("shell_regexes", []))
                if category == "error":
                    regexes = self._normalize_error_patterns(regexes)
                result[category] = regexes + shell_regexes
        return result

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

    def compose(self) -> ComposeResult:
        yield HeaderBar()
        with Horizontal(id="main-content"):
            yield SessionSidebar()
            with Vertical(id="right-panel"):
                yield SessionViewer()
                yield SessionSearchBar()
        yield StatusBar()
        yield ToastOverlay()

    def on_mount(self) -> None:
        loop = asyncio.get_running_loop()
        self._session_manager.attach_to_loop(loop)
        self.call_later(self._restore_tmux_sessions_async)
        self._start_resource_poll()
        self._start_tmux_health_check()
        self._update_memory_status()
        log.info("TAME started")

    # ------------------------------------------------------------------
    # Session status change callback (from SessionManager, may be called
    # from a non-main thread via PTY reader)
    # ------------------------------------------------------------------

    def _handle_status_change(
        self,
        session_id: str,
        old_state: SessionState,
        new_state: SessionState,
        matched_text: str = "",
    ) -> None:
        self.post_message(
            SessionStatusChanged(session_id, old_state.value, new_state.value)
        )
        # Record to Letta memory
        if self._memory_bridge:
            try:
                session = self._session_manager.get_session(session_id)
                session_name = session.name
            except KeyError:
                session_name = session_id
            if new_state == SessionState.ERROR:
                self._memory_bridge.record_error(session_name, matched_text)
            else:
                self._memory_bridge.record_status_change(
                    session_name, old_state.value, new_state.value, matched_text
                )
        event_type = EVENT_TYPE_FOR_STATE.get(new_state)
        if event_type:
            session = self._session_manager.get_session(session_id)
            msg = f"Session '{session.name}' is now {new_state.value}"
            if matched_text:
                msg += f": {matched_text}"
            self._notification_engine.dispatch(
                event_type=event_type,
                session_id=session_id,
                session_name=session.name,
                message=msg,
                matched_text=matched_text,
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
        self._pending_status_updates.add(event.session_id)
        if not self._status_update_scheduled:
            self._status_update_scheduled = True
            self.set_timer(0.05, self._flush_status_updates, name="status_debounce")

    def _flush_status_updates(self) -> None:
        """Batch-apply all pending sidebar/header/status-bar updates."""
        self._status_update_scheduled = False
        pending = self._pending_status_updates.copy()
        self._pending_status_updates.clear()
        sidebar = self.query_one(SessionSidebar)
        header = self.query_one(HeaderBar)
        for sid in pending:
            try:
                session = self._session_manager.get_session(sid)
            except KeyError:
                continue
            sidebar.update_session(session)
            if sid == self._active_session_id:
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
        pass  # PTY resize now handled by on_viewer_resized

    def on_viewer_resized(self, message: ViewerResized) -> None:
        if self._active_session_id is None:
            return
        try:
            self._session_manager.resize_session(
                self._active_session_id, message.rows, message.cols
            )
        except (KeyError, RuntimeError):
            pass

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

        # --- Input history tracking ---
        sid = self._active_session_id
        if pty_input == "\r":
            # Enter: flush accumulated chars as a history entry
            buf = self._input_line_buffer.pop(sid, [])
            if buf:
                line = "".join(buf).strip()
                if line:
                    if line == "pls pls fix" and not self._easter_egg_shown:
                        self._easter_egg_shown = True
                        self.push_screen(EasterEgg())
                    self._record_input_history(sid, line)
        elif pty_input == "\x7f":
            # Backspace: pop last char from buffer
            buf = self._input_line_buffer.get(sid, [])
            if buf:
                buf.pop()
        elif pty_input == "\x03":
            # Ctrl+C: discard current input
            self._input_line_buffer.pop(sid, None)
        elif len(pty_input) == 1 and pty_input.isprintable():
            self._input_line_buffer.setdefault(sid, []).append(pty_input)

        try:
            self._session_manager.send_input(self._active_session_id, pty_input)
        except OSError:
            log.debug("Send to dead session %s ignored", self._active_session_id)
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
        self.push_screen(
            NameDialog(
                default_name,
                show_branch=self._worktrees_enabled,
            ),
            callback=self._create_session,
        )

    def _create_session(self, result) -> None:
        if result is None:
            return
        if isinstance(result, tuple):
            name = result[0]
            profile = result[1] if len(result) > 1 else ""
            branch = result[2] if len(result) > 2 else ""
        else:
            name, profile, branch = result, "", ""

        working_dir = self._default_working_dir
        if not os.path.isdir(working_dir):
            working_dir = os.path.expanduser("~")

        # Create git worktree if branch was specified
        worktree_path = ""
        if branch and self._worktrees_enabled:
            from tame.git.worktree import create_worktree

            wt_path, err = create_worktree(self._git_repo_dir, branch, new_branch=True)
            if err:
                # Try attaching to existing branch
                wt_path, err = create_worktree(
                    self._git_repo_dir, branch, new_branch=False
                )
            if err:
                log.warning("Failed to create worktree for branch %r: %s", branch, err)
                try:
                    toast = self.query_one(ToastOverlay)
                    toast.show_toast(title="Worktree Error", message=err)
                except Exception:
                    pass
            elif wt_path:
                worktree_path = wt_path
                working_dir = wt_path
                log.info("Created worktree at %s for branch %s", wt_path, branch)

        command = self._build_session_command(name)
        viewer = self.query_one(SessionViewer)
        rows = max(1, viewer.size.height) if viewer.size.height else 24
        cols = max(1, viewer.size.width) if viewer.size.width else 80
        session = self._session_manager.create_session(
            name,
            working_dir,
            shell=self._default_shell,
            command=command,
            rows=rows,
            cols=cols,
            profile=profile,
        )
        tmux_session_name = self._build_tmux_session_name(name)
        if command and tmux_session_name:
            session.metadata["tmux_session_name"] = tmux_session_name
        if worktree_path:
            session.metadata["worktree_path"] = worktree_path
            session.metadata["worktree_branch"] = branch

        sidebar = self.query_one(SessionSidebar)
        sidebar.add_session(session)
        self._select_session(session.id)
        self._update_status_bar()
        if self._memory_bridge:
            self._memory_bridge.record_session_created(session.name, working_dir)
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

    def action_toggle_theme(self) -> None:
        new_theme = self._theme_manager.cycle()
        colors = self._theme_manager.get_colors()
        bg, fg = colors["screen"]
        self.screen.styles.background = bg
        self.screen.styles.color = fg
        for widget_key, widget_id in (
            ("header", "header-bar"),
            ("viewer", "session-viewer"),
            ("status", "status-bar"),
        ):
            wbg, wfg = colors[widget_key]
            try:
                widget = self.query_one(f"#{widget_id}")
                widget.styles.background = wbg
                widget.styles.color = wfg
            except Exception:
                pass
        # Sidebar is queried by type (no fixed ID)
        sbg, sfg = colors["sidebar"]
        try:
            sidebar = self.query_one(SessionSidebar)
            sidebar.styles.background = sbg
            sidebar.styles.color = sfg
        except Exception:
            pass
        log.info("Switched theme to '%s'", new_theme)

    def action_delete_session(self) -> None:
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

    def _confirm_kill_session(self, confirmed: bool | None) -> None:
        if not confirmed:
            return
        session_id = self._active_session_id
        if session_id is None:
            return

        # Determine the neighbor to switch to before removing the session
        sessions = self._session_manager.list_sessions()
        ids = [s.id for s in sessions]
        next_session_id: str | None = None
        try:
            idx = ids.index(session_id)
            if len(ids) > 1:
                # Prefer the next session, fall back to previous
                next_session_id = ids[idx + 1] if idx + 1 < len(ids) else ids[idx - 1]
        except ValueError:
            pass

        # Clean up git worktree if one was created for this session
        try:
            session = self._session_manager.get_session(session_id)
            wt_path = session.metadata.get("worktree_path")
            if wt_path:
                from tame.git.worktree import remove_worktree

                err = remove_worktree(self._git_repo_dir, wt_path)
                if err:
                    log.warning("Failed to remove worktree %s: %s", wt_path, err)
                else:
                    log.info("Removed worktree %s", wt_path)
        except KeyError:
            pass

        # Record session end to Letta memory
        if self._memory_bridge:
            try:
                session = self._session_manager.get_session(session_id)
                duration = (
                    datetime.now(timezone.utc) - session.created_at
                ).total_seconds()
                self._memory_bridge.record_session_ended(
                    session.name, session.exit_code, duration
                )
            except KeyError:
                pass

        try:
            self._session_manager.delete_session(session_id)
        except KeyError:
            pass

        sidebar = self.query_one(SessionSidebar)
        viewer = self.query_one(SessionViewer)

        sidebar.remove_session(session_id)
        viewer.remove_session(session_id)

        # Switch to the nearest neighbor or clear
        if next_session_id is not None:
            self._select_session(next_session_id)
        else:
            self._active_session_id = None
            header = self.query_one(HeaderBar)
            header.clear_session()

        self._update_status_bar()
        log.info("Killed session %s", session_id)

    def action_rename_session(self) -> None:
        """Open a name dialog to rename the active session."""
        if isinstance(self.screen, (NameDialog, ConfirmDialog, CommandPalette)):
            return
        if self._active_session_id is None:
            return
        try:
            session = self._session_manager.get_session(self._active_session_id)
        except KeyError:
            return
        self.push_screen(
            NameDialog(session.name, show_profile=False),
            callback=self._confirm_rename_session,
        )

    def _confirm_rename_session(self, result) -> None:
        if result is None:
            return
        new_name = result[0] if isinstance(result, tuple) else result
        session_id = self._active_session_id
        if session_id is None:
            return
        self._session_manager.rename_session(session_id, new_name)
        try:
            session = self._session_manager.get_session(session_id)
        except KeyError:
            return
        sidebar = self.query_one(SessionSidebar)
        sidebar.update_session(session)
        header = self.query_one(HeaderBar)
        header.update_from_session(session)
        # Rename tmux session if applicable
        tmux_name = session.metadata.get("tmux_session_name")
        if tmux_name:
            new_tmux = self._build_tmux_session_name(new_name)
            if new_tmux:
                subprocess.run(
                    ["tmux", "rename-session", "-t", tmux_name, new_tmux],
                    capture_output=True,
                    check=False,
                )
                session.metadata["tmux_session_name"] = new_tmux
        log.info("Renamed session %s to '%s'", session_id, new_name)

    def action_set_group(self) -> None:
        """Open a dialog to assign the active session to a group."""
        if isinstance(
            self.screen, (NameDialog, ConfirmDialog, CommandPalette, GroupDialog)
        ):
            return
        if self._active_session_id is None:
            return
        try:
            session = self._session_manager.get_session(self._active_session_id)
        except KeyError:
            return
        self.push_screen(
            GroupDialog(session.group),
            callback=self._confirm_set_group,
        )

    def _confirm_set_group(self, group: str | None) -> None:
        if group is None:
            return
        session_id = self._active_session_id
        if session_id is None:
            return
        self._session_manager.set_session_group(session_id, group)
        try:
            session = self._session_manager.get_session(session_id)
        except KeyError:
            return
        sidebar = self.query_one(SessionSidebar)
        sidebar.update_session(session)
        log.info("Set group for session %s to '%s'", session_id, group)

    def action_export_session(self) -> None:
        """Export the active session's output buffer to a text file."""
        if self._active_session_id is None:
            return
        try:
            session = self._session_manager.get_session(self._active_session_id)
        except KeyError:
            return
        text = session.output_buffer.get_all_text()
        if not text:
            try:
                toast = self.query_one(ToastOverlay)
                toast.show_toast(title="Export", message="No output to export")
            except Exception:
                pass
            return
        safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", session.name).strip("_") or "session"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_name}_{timestamp}.txt"
        export_dir = os.path.expanduser("~/.local/share/tame/exports")
        os.makedirs(export_dir, exist_ok=True)
        filepath = os.path.join(export_dir, filename)
        # Strip ANSI escape sequences for clean text export
        clean_text = re.sub(
            r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x1B\x07]*(?:\x07|\x1B\\))",
            "",
            text,
        )
        with open(filepath, "w") as f:
            f.write(clean_text)
        try:
            toast = self.query_one(ToastOverlay)
            toast.show_toast(title="Export", message=f"Saved to {filepath}")
        except Exception:
            pass
        log.info("Exported session '%s' to %s", session.name, filepath)

    def _record_input_history(self, session_id: str, line: str) -> None:
        """Save a line to the session's input history (deduplicated at head)."""
        try:
            session = self._session_manager.get_session(session_id)
        except KeyError:
            return
        # Avoid consecutive duplicates
        if session.input_history and session.input_history[-1] == line:
            return
        session.input_history.append(line)
        # Cap history at 500 entries
        if len(session.input_history) > 500:
            session.input_history[:] = session.input_history[-500:]

    def action_show_history(self) -> None:
        """Open a picker showing cross-session input history."""
        # Gather history from all sessions, most recent last
        all_entries: list[str] = []
        for session in self._session_manager.list_sessions():
            all_entries.extend(session.input_history)
        self.push_screen(HistoryPicker(all_entries), callback=self._handle_history_pick)

    def _handle_history_pick(self, command: str | None) -> None:
        if command is None or self._active_session_id is None:
            return
        # Send the selected command to the active session (with Enter)
        self._session_manager.send_input(self._active_session_id, command + "\r")
        self._record_input_history(self._active_session_id, command)

    def action_check_usage(self) -> None:
        """Send a usage command to the active session to trigger usage parsing."""
        if self._active_session_id is None:
            return
        try:
            session = self._session_manager.get_session(self._active_session_id)
        except KeyError:
            return
        # If we already have usage info, show it via toast
        if session.usage.model_name or session.usage.tokens_used is not None:
            parts = []
            if session.usage.model_name:
                parts.append(f"Model: {session.usage.model_name}")
            if session.usage.tokens_used is not None:
                parts.append(f"Tokens: {session.usage.tokens_used:,}")
            if session.usage.quota_remaining:
                parts.append(f"Remaining: {session.usage.quota_remaining}")
            if session.usage.refresh_time:
                parts.append(f"Resets: {session.usage.refresh_time}")
            msg = " | ".join(parts) if parts else "No usage data available"
            try:
                toast = self.query_one(ToastOverlay)
                toast.show_toast(title="Usage Info", message=msg)
            except Exception:
                pass

    def action_send_sigint(self) -> None:
        """Forward Ctrl+C as SIGINT to the active PTY session."""
        if isinstance(self.screen, (NameDialog, ConfirmDialog, CommandPalette)):
            return
        if self._active_session_id is None:
            return
        self._session_manager.send_input(self._active_session_id, "\x03")

    def action_send_eof(self) -> None:
        """Forward Ctrl+D (EOF) to the active PTY session."""
        if isinstance(self.screen, (NameDialog, ConfirmDialog, CommandPalette)):
            return
        if self._active_session_id is None:
            return
        self._session_manager.send_input(self._active_session_id, "\x04")

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

    def action_global_search(self) -> None:
        """Open a global search dialog across all session output buffers."""
        if isinstance(
            self.screen, (NameDialog, ConfirmDialog, CommandPalette, SearchDialog)
        ):
            return
        sessions_data: list[tuple[str, str, str]] = []
        for session in self._session_manager.list_sessions():
            sessions_data.append(
                (session.id, session.name, session.output_buffer.get_all_text())
            )
        self.push_screen(
            SearchDialog(sessions_data),
            callback=self._handle_search_result,
        )

    def _handle_search_result(self, session_id: str | None) -> None:
        if session_id is not None:
            self._select_session(session_id)

    def action_show_diff(self) -> None:
        """Show git diff for the active session's working directory."""
        if isinstance(
            self.screen, (NameDialog, ConfirmDialog, CommandPalette, DiffViewer)
        ):
            return
        if self._active_session_id is None:
            return
        try:
            session = self._session_manager.get_session(self._active_session_id)
        except KeyError:
            return
        from tame.git.diff import git_diff

        result = git_diff(session.working_dir)
        self.push_screen(DiffViewer(result, title=f"Diff: {session.name}"))

    # ------------------------------------------------------------------
    # Letta memory actions
    # ------------------------------------------------------------------

    def action_toggle_memory(self) -> None:
        """Toggle session memory on/off."""
        if not self._letta_available():
            self._show_toast(
                "Memory",
                "letta-client not installed. Run: pip install tame[memory]",
            )
            return
        if self._memory_bridge is None:
            # First-time init (shouldn't normally happen if letta is installed)
            cfg = self._config_manager.config
            from tame.integrations.letta import MemoryBridge

            letta_cfg = cfg.get("letta", {})
            server_url = str(letta_cfg.get("server_url", "http://localhost:8283"))
            self._memory_bridge = MemoryBridge(server_url)

        if not self._memory_ever_enabled:
            # First time — show onboarding dialog
            server_url = self._memory_bridge._server_url
            self.push_screen(
                MemoryEnableDialog(server_url),
                callback=self._handle_memory_enable,
            )
        else:
            # Subsequent toggle — quick on/off
            new_state, msg = self._memory_bridge.toggle()
            self._show_toast("Memory", msg)
            self._update_memory_status()

    def _handle_memory_enable(self, confirmed: bool | None) -> None:
        if not confirmed or self._memory_bridge is None:
            return
        ok, msg = self._memory_bridge.enable()
        self._show_toast("Memory", msg)
        if ok:
            self._memory_ever_enabled = True
            # Persist enabled state to config
            cfg = self._config_manager.config
            cfg.setdefault("letta", {})["enabled"] = True
            self._config_manager.save(cfg)
        self._update_memory_status()

    def action_recall_memory(self) -> None:
        """Open the memory recall dialog to query past session events."""
        if not self._letta_available() or self._memory_bridge is None:
            self._show_toast(
                "Memory",
                "Memory not available. Toggle memory on first.",
            )
            return
        if not self._memory_bridge.is_connected:
            self._show_toast(
                "Memory",
                "Memory not connected. Toggle memory on first.",
            )
            return
        self.push_screen(MemoryRecallDialog())

    def action_clear_memory(self) -> None:
        """Open confirmation dialog to clear all session memory."""
        if not self._letta_available() or self._memory_bridge is None:
            self._show_toast("Memory", "Memory not available.")
            return
        if not self._memory_bridge.is_connected:
            self._show_toast("Memory", "Memory not connected.")
            return
        self.push_screen(
            MemoryClearDialog(),
            callback=self._handle_memory_clear,
        )

    async def _handle_memory_clear(self, confirmed: bool | None) -> None:
        if not confirmed or self._memory_bridge is None:
            return
        ok, msg = await self._memory_bridge.clear()
        self._show_toast("Memory", msg)

    def _update_memory_status(self) -> None:
        """Update the status bar memory indicator."""
        if self._memory_bridge is None:
            status = ""
        else:
            raw = self._memory_bridge.status
            if raw == "on":
                status = "On"
            elif raw == "err":
                status = "\u26a0"
            else:
                status = "Off"
        try:
            bar = self.query_one(StatusBar)
            bar.set_memory_status(status)
        except Exception:
            pass

    def _show_toast(self, title: str, message: str) -> None:
        try:
            toast = self.query_one(ToastOverlay)
            toast.show_toast(title=title, message=message)
        except Exception:
            pass

    def action_session_search(self) -> None:
        """Toggle the in-session search bar."""
        if isinstance(self.screen, (NameDialog, ConfirmDialog, CommandPalette)):
            return
        search_bar = self.query_one(SessionSearchBar)
        if search_bar.visible:
            search_bar.hide()
        else:
            search_bar.show()

    def action_notification_history(self) -> None:
        """Open the notification history panel."""
        if isinstance(
            self.screen, (NameDialog, ConfirmDialog, CommandPalette, NotificationPanel)
        ):
            return
        history = self._notification_engine.get_history()
        self.push_screen(
            NotificationPanel(history),
            callback=self._handle_notification_panel_result,
        )

    def _handle_notification_panel_result(self, session_id: str | None) -> None:
        if session_id is not None:
            self._select_session(session_id)

    # ------------------------------------------------------------------
    # In-session search message handlers
    # ------------------------------------------------------------------

    def on_search_query_changed(self, event: SearchQueryChanged) -> None:
        viewer = self.query_one(SessionViewer)
        total = viewer.set_search_highlights(event.query, event.is_regex)
        search_bar = self.query_one(SessionSearchBar)
        search_bar.update_match_count(viewer.current_match_index, total)

    def on_search_navigate(self, event: SearchNavigate) -> None:
        viewer = self.query_one(SessionViewer)
        idx = viewer.navigate_search(event.forward)
        search_bar = self.query_one(SessionSearchBar)
        search_bar.update_match_count(idx, viewer.match_count)

    def on_search_dismissed(self, event: SearchDismissed) -> None:
        viewer = self.query_one(SessionViewer)
        viewer.clear_search_highlights()
        viewer.focus()

    def action_focus_search(self) -> None:
        if isinstance(self.screen, (NameDialog, ConfirmDialog, CommandPalette)):
            return
        sidebar = self.query_one(SessionSidebar)
        search_input = sidebar.query_one("#session-search", Input)
        search_input.focus()

    def action_focus_input(self) -> None:
        if isinstance(self.screen, (NameDialog, ConfirmDialog, CommandPalette)):
            return
        try:
            self.query_one(SessionViewer).focus()
        except Exception:
            pass

    def _select_session_by_index(self, index: int) -> None:
        """Select the Nth session (0-based) from the session list."""
        sessions = self._session_manager.list_sessions()
        if index < len(sessions):
            self._select_session(sessions[index].id)

    def action_session_1(self) -> None:
        self._select_session_by_index(0)

    def action_session_2(self) -> None:
        self._select_session_by_index(1)

    def action_session_3(self) -> None:
        self._select_session_by_index(2)

    def action_session_4(self) -> None:
        self._select_session_by_index(3)

    def action_session_5(self) -> None:
        self._select_session_by_index(4)

    def action_session_6(self) -> None:
        self._select_session_by_index(5)

    def action_session_7(self) -> None:
        self._select_session_by_index(6)

    def action_session_8(self) -> None:
        self._select_session_by_index(7)

    def action_session_9(self) -> None:
        self._select_session_by_index(8)

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
        self._refresh_viewer_from_tmux_snapshot(session)
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
    # PTY output -> UI (batched, focus-aware)
    # ------------------------------------------------------------------

    def _handle_pty_output(self, session_id: str, text: str) -> None:
        """Accumulate PTY output; flush immediately for small output (echo),
        batch at 16ms for bulk output."""
        self._output_pending.setdefault(session_id, []).append(text)
        if not self._app_focused:
            return
        # Redraw-heavy control chunks (cursor movement / clear / CR redraw)
        # are latency-sensitive and can artifact if delayed behind batching.
        if session_id == self._active_session_id and self._is_redraw_control_chunk(
            text
        ):
            if self._output_flush_timer is not None:
                self._output_flush_timer.stop()
                self._output_flush_timer = None
            self._flush_pending_output()
            return
        # Small output (keystroke echo): flush immediately
        total = sum(len(c) for chunks in self._output_pending.values() for c in chunks)
        if total <= 64:
            if self._output_flush_timer is not None:
                self._output_flush_timer.stop()
                self._output_flush_timer = None
            self._flush_pending_output()
        elif self._output_flush_timer is None:
            self._output_flush_timer = self.set_timer(
                0.016, self._flush_pending_output, name="output_flush"
            )

    @staticmethod
    def _is_redraw_control_chunk(text: str) -> bool:
        return bool(REDRAW_CONTROL_RE.search(text))

    def _flush_pending_output(self) -> None:
        """Drain accumulated output — one pyte.feed() per session."""
        self._output_flush_timer = None
        pending = self._output_pending
        if not pending:
            return
        self._output_pending = {}

        viewer = self.query_one(SessionViewer)
        for session_id, chunks in pending.items():
            combined = "".join(chunks)
            if session_id == self._active_session_id:
                try:
                    session = self._session_manager.get_session(session_id)
                except KeyError:
                    continue
                if not self._refresh_viewer_from_tmux_snapshot(session):
                    viewer.append_output(combined)
            else:
                # Background session: discard cached pyte state so it
                # rebuilds from OutputBuffer when the user switches to it.
                viewer.invalidate_session(session_id)

    def on_app_blur(self, event: events.AppBlur) -> None:
        """App lost focus — pause output processing to avoid hidden work."""
        self._app_focused = False
        if self._output_flush_timer is not None:
            self._output_flush_timer.stop()
            self._output_flush_timer = None

    def on_app_focus(self, event: events.AppFocus) -> None:
        """App regained focus — flush any accumulated output in one batch."""
        self._app_focused = True
        self._flush_pending_output()

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
        viewer = self.query_one(SessionViewer)
        rows = max(1, viewer.size.height) if viewer.size.height else 24
        cols = max(1, viewer.size.width) if viewer.size.width else 80
        for tmux_session in tmux_sessions:
            display_name = self._display_name_for_tmux_session(tmux_session)
            try:
                session = self._session_manager.create_session(
                    display_name,
                    working_dir,
                    shell=self._default_shell,
                    command=["tmux", "attach-session", "-t", tmux_session],
                    rows=rows,
                    cols=cols,
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
        viewer = self.query_one(SessionViewer)
        rows = max(1, viewer.size.height) if viewer.size.height else 24
        cols = max(1, viewer.size.width) if viewer.size.width else 80
        restored_count = 0
        for tmux_session in tmux_sessions:
            display_name = self._display_name_for_tmux_session(tmux_session)
            try:
                session = self._session_manager.create_session(
                    display_name,
                    working_dir,
                    shell=self._default_shell,
                    command=["tmux", "attach-session", "-t", tmux_session],
                    rows=rows,
                    cols=cols,
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

    def _capture_tmux_pane_render(self, tmux_session: str) -> str | None:
        """Capture a tmux pane snapshot for stable text rendering."""
        proc = subprocess.run(
            ["tmux", "capture-pane", "-p", "-e", "-t", tmux_session],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return None
        return self._sanitize_tmux_snapshot_ansi(proc.stdout)

    @staticmethod
    def _sanitize_tmux_snapshot_ansi(text: str) -> str:
        """Keep foreground styling while stripping background/reverse SGR attrs."""

        def _repl(match: re.Match[str]) -> str:
            params = match.group(1)
            if params == "":
                return match.group(0)  # ESC[m == reset
            parts = params.split(";")
            kept: list[str] = []
            i = 0
            while i < len(parts):
                part = parts[i]
                if part == "":
                    kept.append(part)
                    i += 1
                    continue
                if not part.isdigit():
                    kept.append(part)
                    i += 1
                    continue
                code = int(part)

                # Strip reverse-video toggles.
                if code in (7, 27):
                    i += 1
                    continue
                # Strip background default + classic/bright background palette.
                if code == 49 or 40 <= code <= 47 or 100 <= code <= 107:
                    i += 1
                    continue
                # Strip extended background color sequences: 48;5;N / 48;2;R;G;B.
                if code == 48:
                    if (
                        i + 1 < len(parts)
                        and parts[i + 1] == "5"
                        and i + 2 < len(parts)
                    ):
                        i += 3
                        continue
                    if (
                        i + 1 < len(parts)
                        and parts[i + 1] == "2"
                        and i + 4 < len(parts)
                    ):
                        i += 5
                        continue
                    i += 1
                    continue

                kept.append(part)
                i += 1

            if not kept:
                return ""
            return f"\x1b[{';'.join(kept)}m"

        return SGR_RE.sub(_repl, text)

    def _refresh_viewer_from_tmux_snapshot(self, session) -> bool:
        if not (self._tmux_snapshot_render and self._tmux_available):
            return False
        tmux_session = session.metadata.get("tmux_session_name")
        if not tmux_session:
            return False
        snapshot = self._capture_tmux_pane_render(str(tmux_session))
        if snapshot is None:
            return False
        self.query_one(SessionViewer).show_snapshot(snapshot)
        return True

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
            return tmux_session[len(prefix) :]
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
    # Resource monitoring (#17)
    # ------------------------------------------------------------------

    def _start_resource_poll(self) -> None:
        """Start periodic resource polling for the active session."""
        cfg = self._config_manager.config
        interval = float(cfg.get("sessions", {}).get("resource_poll_seconds", 5))
        self._resource_poll_interval = interval
        self.set_interval(interval, self._poll_resources_async, name="resource_poll")

    async def _poll_resources_async(self) -> None:
        """Run resource polling in executor to avoid blocking the event loop."""
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, self._collect_resource_data)
        self._apply_resource_data(results)

    def _collect_resource_data(self) -> list[tuple[str, float, str]]:
        """Collect CPU/MEM data for all sessions (runs in thread)."""
        try:
            import psutil
        except ImportError:
            return []

        data: list[tuple[str, float, str]] = []
        for session in self._session_manager.list_sessions():
            if session.pid is None:
                continue
            try:
                proc = psutil.Process(session.pid)
                cpu = proc.cpu_percent(interval=0)
                mem_info = proc.memory_info()
                mem_mb = mem_info.rss / (1024 * 1024)
                if mem_mb >= 1024:
                    mem_str = f"{mem_mb / 1024:.1f}GB"
                else:
                    mem_str = f"{mem_mb:.0f}MB"
                data.append((session.id, cpu, mem_str))
            except Exception:
                pass
        return data

    def _apply_resource_data(self, results: list[tuple[str, float, str]]) -> None:
        """Apply collected resource data to UI widgets (runs on main thread)."""
        from tame.ui.widgets.session_list_item import SessionListItem

        for session_id, cpu, mem_str in results:
            try:
                item = self.query_one(f"#session-item-{session_id}", SessionListItem)
                item.update_resources(cpu, mem_str)
            except Exception:
                pass
            if session_id == self._active_session_id:
                try:
                    header = self.query_one(HeaderBar)
                    header.update_system_stats(cpu, mem_str)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Tmux health check
    # ------------------------------------------------------------------

    def _start_tmux_health_check(self) -> None:
        """Periodically verify tmux sessions are still alive."""
        if not (self._start_in_tmux and self._tmux_available):
            return
        self.set_interval(30.0, self._check_tmux_health, name="tmux_health")

    async def _check_tmux_health(self) -> None:
        """Check each tmux-backed session is still alive."""
        loop = asyncio.get_running_loop()
        for session in self._session_manager.list_sessions():
            tmux_name = session.metadata.get("tmux_session_name")
            if not tmux_name:
                continue
            if session.status in (SessionState.DONE, SessionState.ERROR):
                continue
            alive = await loop.run_in_executor(
                None, self._tmux_session_alive, str(tmux_name)
            )
            if not alive:
                log.warning("Tmux session %r gone — marking EXITED", tmux_name)
                self._session_manager.mark_session_exited(session.id)

    @staticmethod
    def _tmux_session_alive(tmux_name: str) -> bool:
        proc = subprocess.run(
            ["tmux", "has-session", "-t", tmux_name],
            capture_output=True,
            check=False,
        )
        return proc.returncode == 0

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def on_unmount(self) -> None:
        self._session_manager.close_all()
