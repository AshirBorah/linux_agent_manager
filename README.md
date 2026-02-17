[![CI](https://github.com/AshirBorah/linux_agent_manager/actions/workflows/ci.yml/badge.svg)](https://github.com/AshirBorah/linux_agent_manager/actions/workflows/ci.yml)

# TAME — Terminal Agent Management Environment

An intelligent terminal multiplexer for managing multiple parallel AI agent sessions. Think tmux, but aware that AI agents are running and needing attention.

TAME does **not** launch or orchestrate agents. You create PTY-backed shell sessions and run whatever CLI agent you want (`claude`, `codex`, `aider`, `gemini`, a custom script, etc.). TAME monitors the PTY output of each session using configurable regex patterns and notifies you when something needs your attention.

## Features

### Session management
- Create, switch, rename, pause (SIGSTOP), resume (SIGCONT), and delete terminal sessions
- Batch pause/resume all sessions at once
- Session groups — organize sessions into named, collapsible groups
- Session export — save full session output to a timestamped text file

### Pattern-based status detection
- Configurable regexes detect prompts, errors, completion, progress, and weak prompts
- **Agent-specific profiles** — built-in pattern sets for `claude`, `codex`, and `training` workloads; select a profile when creating a session
- **Batch "last match wins"** — within a single output chunk, the final matching pattern determines the state (e.g. an error on line 1 followed by a prompt on line 5 yields WAITING, not ERROR)
- **Weak prompt timeout gating** — lines ending in `?` are treated as weak prompts; TAME waits a configurable timeout (default 3 s) before promoting to WAITING, cancelling if new output arrives
- **State machine debounce** — 500 ms debounce window prevents flicker on rapid transitions; priority states (ERROR_SEEN, NEEDS_INPUT) bypass debounce

### Smart notifications
- **Desktop** — `notify-send` (Linux) / `osascript` (macOS) with urgency levels
- **Audio** — pygame, simpleaudio, or terminal bell fallback
- **In-app toasts** — auto-dismissing overlay notifications
- **Sidebar flash** — visual alert on the sidebar for the session that needs attention
- **Slack** — webhook integration with verbosity filtering (errors-only to everything)
- **Generic webhooks** — JSON POST to any URL with custom headers
- **Do Not Disturb** — time-range DND mode suppresses all channels
- Per-event cooldowns prevent notification storms

### Terminal emulation
- **Full PTY** — each session runs in a real pseudo-terminal (`pty.openpty()`) with proper signal handling
- **VT100 emulation** — pyte-based `TAMEScreen` with alternate screen buffer support (modes 47, 1047, 1048, 1049)
- **Tmux snapshot rendering** — captures and renders tmux pane content with ANSI sanitization
- **Keystroke passthrough** — arrow keys, Ctrl sequences, Alt combos, Tab, function keys all forwarded to the active PTY
- **Async I/O** — `loop.add_reader()` epoll integration with Textual's asyncio loop; no threads
- **UTF-8 safety** — per-session incremental decoders handle multi-byte characters split across PTY reads

### Usage tracking
Auto-detects AI CLI usage info from output:
- Messages remaining (e.g. "Opus messages: 42/100 remaining")
- Token counts
- Model name
- Rate-limit reset times

Displayed in the header bar; press `u` in the command palette to check.

### Git integration
- **Worktree support** — list, create, and remove git worktrees; optionally select a branch when creating a session
- **Diff viewer** — F10 opens a modal showing the current working-tree diff with syntax coloring

### Resource monitoring
- Per-session CPU % and memory (RSS) via psutil, displayed in the sidebar and header bar
- Configurable polling interval (default 5 s)

### Global search
- Ctrl+F searches across all session output buffers
- Results shown with session name, line number, and matching text

### Themes
8 built-in themes: `dark`, `light`, `dracula`, `nord`, `monokai`, `gruvbox`, `solarized_dark`, `solarized_light`. Cycle with Ctrl+T or the command palette. Custom CSS paths supported.

### Configuration
`~/.config/tame/config.toml` — created with sensible defaults on first run. Deep-merge: user overrides are layered on top of defaults.

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

| Key              | Action              |
|------------------|---------------------|
| F2               | New session          |
| F3 / F4          | Prev / Next session  |
| F6               | Toggle sidebar       |
| F7 / F8          | Resume / Pause all   |
| F9               | Rename session       |
| F10              | Git diff viewer      |
| F11              | Set session group    |
| Alt+1 ... Alt+9  | Jump to session N    |
| Ctrl+Space       | Command palette      |
| Ctrl+F           | Global search        |
| Ctrl+T           | Cycle theme          |
| Ctrl+L           | Focus input          |
| Shift+Tab        | Focus search         |
| Ctrl+C           | Send SIGINT to PTY   |
| Ctrl+D           | Send EOF to PTY      |
| Tab              | Send tab to PTY      |
| F12              | Quit                 |

All other keystrokes are forwarded to the active session's PTY. Key bindings are configurable via `[keybindings]` in config.

#### Command palette

Press `Ctrl+Space` then one of:

| Key | Action              |
|-----|---------------------|
| c   | New session          |
| d   | Delete session       |
| e   | Export session log   |
| g   | Set session group    |
| h   | Input history picker |
| m   | Rename session       |
| n   | Next session         |
| p   | Previous session     |
| s   | Toggle sidebar       |
| f   | Focus search         |
| i   | Focus input          |
| t   | Cycle theme          |
| u   | Check usage          |
| r   | Resume all           |
| z   | Pause all            |
| x   | Clear notifications  |
| 1-9 | Jump to session N    |
| q   | Quit                 |

## Configuration

On first run, TAME creates `~/.config/tame/config.toml` with defaults. Key sections:

```toml
[sessions]
default_working_directory = "~"
start_in_tmux = true                     # back each session with a tmux session
restore_tmux_sessions_on_startup = true  # auto-restore on launch
tmux_session_prefix = "tame"
idle_threshold_seconds = 300             # seconds before IDLE state

[patterns.prompt]
regexes = ['\\[y/n\\]', '\\[Y/n\\]', '\\[yes/no\\]']

[patterns.error]
regexes = ['(?i)error:', '(?i)fatal:', 'Traceback \\(most recent call last\\)']
shell_regexes = ['command not found', 'No such file or directory']

[patterns.profiles.claude]
prompt = ['(?i)approve|deny', '(?i)do you want to proceed']
error  = ['(?i)api error', '(?i)rate limit']

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
[notifications.slack]
enabled = false
webhook_url = ""
verbosity = 10                           # 0=off, 10=errors+input, 50=+completed, 100=all

[theme]
current = "dark"

[git]
worktrees_enabled = true

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
├── config/                   # ConfigManager, defaults, profiles
├── session/                  # SessionManager, PTY, OutputBuffer, PatternMatcher, state machine
├── ui/widgets/               # Sidebar, Viewer, HeaderBar, StatusBar, dialogs, overlays
├── ui/themes/                # ThemeManager + .tcss files
├── ui/keys/                  # KeybindManager
├── notifications/            # NotificationEngine, desktop, audio, toast, Slack, webhook
├── persistence/              # StateStore (SQLite)
├── git/                      # Git worktree helpers
└── utils/                    # Logging
tests/                        # pytest tests (221+)
```

### Planned (v2)

- Docker container sessions
- Plugin system
- Web UI

## License

MIT
