# TAME — Terminal Agent Management Environment

An intelligent terminal multiplexer for managing multiple parallel AI agent sessions. Think tmux, but aware that AI agents are running and needing attention.

TAME does **not** launch or orchestrate agents. You create PTY-backed shell sessions and run whatever CLI agent you want (`claude`, `codex`, `aider`, `gemini`, a custom script, etc.). TAME monitors the PTY output of each session using configurable regex patterns and notifies you when something needs your attention.

## Features

- **Session management** — create, switch, pause, resume, and delete terminal sessions from a sidebar
- **Pattern-based status detection** — configurable regexes detect prompts, errors, completion, and progress
- **Smart notifications** — desktop notifications, audio alerts, in-app toasts, and sidebar flashing when a session needs attention
- **Tmux integration** — optionally back each session with a tmux session for persistence across restarts
- **Keystroke passthrough** — full keyboard input forwarding (arrow keys, Ctrl sequences, Alt combos, Tab) to the active PTY
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
- tmux (optional, for session persistence)

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

All other keystrokes are forwarded to the active session's PTY.

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
start_in_tmux = false
restore_tmux_sessions_on_startup = true

[patterns.prompt]
regexes = ['\\[y/n\\]', '\\[Y/n\\]', '\\?\\s*$']

[patterns.error]
regexes = ['(?i)\\berror\\b[:\\s]', 'Traceback \\(most recent call last\\)']

[notifications]
desktop = true
audio = false
toast = true
```

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
├── persistence/              # SQLite StateStore
└── utils/                    # Logging
tests/                        # pytest tests mirroring src structure
```

## License

MIT
