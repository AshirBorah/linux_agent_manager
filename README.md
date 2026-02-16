[![CI](https://github.com/AshirBorah/linux_agent_manager/actions/workflows/ci.yml/badge.svg)](https://github.com/AshirBorah/linux_agent_manager/actions/workflows/ci.yml)

# TAME — Terminal Agent Management Environment

An intelligent terminal multiplexer for managing multiple parallel AI agent sessions. Think tmux, but aware that AI agents are running and needing attention.

TAME does **not** launch or orchestrate agents. You create PTY-backed shell sessions and run whatever CLI agent you want (`claude`, `codex`, `aider`, `gemini`, a custom script, etc.). TAME monitors the PTY output of each session using configurable regex patterns and notifies you when something needs your attention.

## Features

- **Session management** — create, switch, pause, resume, and delete terminal sessions from a sidebar
- **Pattern-based status detection** — configurable regexes detect prompts, errors, completion, and progress
- **Smart notifications** — desktop notifications, audio alerts, in-app toasts, and sidebar flashing when a session needs attention
- **Tmux-first architecture** — each session is backed by a tmux session for persistence across restarts; TAME auto-restores on startup
- **Keystroke passthrough** — full keyboard input forwarding (arrow keys, Ctrl sequences, Alt combos, Tab) to the active PTY
- **Configurable keybindings** — override any key binding via `~/.config/tame/config.toml`
- **TOML configuration** — `~/.config/tame/config.toml` with sensible defaults that work out of the box

### Status indicators

| Symbol | State     | Meaning                                      |
|--------|-----------|----------------------------------------------|
| `●`    | ACTIVE    | Process is running and producing output       |
| `○`    | IDLE      | No output for the configured idle threshold   |
| `◉`    | WAITING   | Agent detected as waiting for user input      |
| `✗`    | ERROR     | Error pattern matched or non-zero exit        |
| `✓`    | DONE      | Completion pattern matched or clean exit      |
| `⏸`    | PAUSED    | Process suspended via SIGSTOP                 |

## Requirements

- Python 3.11+
- POSIX (Linux, macOS)
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- tmux (recommended — enables session persistence and restore)

## Installation

```bash
git clone https://github.com/AshirBorah/linux_agent_manager.git
cd linux_agent_manager
uv sync
```

## Usage

```bash
uv run tame
```

### Key bindings

| Key         | Action              |
|-------------|---------------------|
| F2          | New session          |
| F3 / F4     | Prev / Next          |
| F6          | Toggle sidebar       |
| F7 / F8     | Resume / Pause all   |
| Ctrl+Space  | Command palette      |
| F12         | Quit                 |
| Shift+Tab   | Focus search         |

All other keystrokes are forwarded to the active session's PTY. Key bindings are configurable via `[keybindings]` in config.

#### Command palette keys

Press `Ctrl+Space` then one of:

| Key | Action              |
|-----|---------------------|
| c   | New session          |
| n   | Next session         |
| p   | Previous session     |
| k   | Kill session         |
| s   | Toggle sidebar       |
| r   | Resume all           |
| z   | Pause all            |
| x   | Clear notifications  |
| q   | Quit                 |

## Configuration

On first run, TAME creates `~/.config/tame/config.toml` with defaults. Key sections:

```toml
[sessions]
default_working_directory = "~"
start_in_tmux = true                     # back each session with a tmux session
restore_tmux_sessions_on_startup = true  # auto-restore on launch
tmux_session_prefix = "tame"

[patterns.prompt]
regexes = ['\\[y/n\\]', '\\[Y/n\\]', '\\[yes/no\\]']

[patterns.error]
regexes = ['(?i)error:', '(?i)fatal:', 'Traceback \\(most recent call last\\)']
shell_regexes = ['command not found', 'No such file or directory']

[notifications]
enabled = true
[notifications.dnd]
enabled = false
start = ""
end = ""
[notifications.desktop]
enabled = true
[notifications.audio]
enabled = true
[notifications.toast]
enabled = true

[keybindings]
new_session = "f2"
prev_session = "f3"
next_session = "f4"
toggle_sidebar = "f6"
quit = "f12"
```

See `tame/config/defaults.py` for the full default configuration.

## Development

```bash
uv pip install pytest pytest-asyncio textual-dev   # install dev deps
uv run pytest                                       # run all tests
uv run pytest tests/ -x --tb=short -v               # verbose, stop on first failure
uv run pytest -k "pattern"                          # run specific tests
```

## Project structure

```
tame/
├── __main__.py               # Entry point
├── app.py                    # TAMEApp (Textual App)
├── config/                   # ConfigManager, defaults
├── session/                  # SessionManager, PTY, OutputBuffer, PatternMatcher
├── ui/widgets/               # Sidebar, Viewer, HeaderBar, StatusBar, etc.
├── ui/themes/                # ThemeManager + .tcss files
├── ui/keys/                  # KeybindManager
├── notifications/            # NotificationEngine, desktop, audio, toast
└── utils/                    # Logging
tests/                        # pytest tests mirroring src structure
```

### Planned (v2)

- Docker container sessions
- VT100 emulation improvements
- Plugin system
- Web UI
- SQLite state persistence
- Resource monitoring (CPU/memory per session)

## License

MIT
