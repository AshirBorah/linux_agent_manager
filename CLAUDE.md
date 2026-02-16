# TAME — Terminal Agent Management Environment

## Project Overview
TAME is an intelligent terminal multiplexer for managing multiple parallel AI agent sessions. Think tmux, but aware that AI agents are running and needing attention. It does NOT launch or orchestrate agents — users create PTY-backed shell sessions and run whatever CLI agent they want.

## Tech Stack
- **Language:** Python 3.11+ (developed on 3.12)
- **UI Framework:** Textual (TUI)
- **Build Tool:** uv
- **Testing:** pytest + Textual pilot
- **Platform:** POSIX (Linux, macOS — PTY, notify-send/osascript, POSIX signals)

## Key Architecture Decisions
- **PTY over PIPE:** Sessions use pseudo-terminals for real-time output, isatty()=True, and proper signal handling
- **Async I/O:** PTY reading via `loop.add_reader(master_fd)` — zero-thread epoll integration with Textual's asyncio loop
- **Line-based input:** v1 uses a text input widget that sends lines on Enter (not raw keystroke passthrough)
- **Pattern matching on output:** Configurable regexes detect prompts, errors, completion, progress — drives notifications
- **SQLite persistence:** Session metadata, output buffers (gzipped), scroll positions
- **TOML config:** `~/.config/tame/config.toml`, created with defaults on first run

## Project Structure
```
tame/                         # Main package
├── __main__.py               # Entry point
├── app.py                    # TAMEApp (Textual App)
├── config/                   # ConfigManager, defaults
├── session/                  # SessionManager, PTY, OutputBuffer, PatternMatcher
├── ui/widgets/               # Textual widgets (sidebar, viewer, input, header, status)
├── ui/themes/                # ThemeManager + .tcss files
├── ui/keys/                  # KeybindManager
├── notifications/            # NotificationEngine, desktop, audio, toast
├── persistence/              # SQLite StateStore
└── utils/                    # Logging
tests/                        # pytest tests mirroring src structure
```

## Development Phases
- **MVP (Phase 1+2):** Shell multiplexer + pattern matching + notifications
- **Phase 3:** Persistence & config
- **Phase 4:** Polish (themes, search, resource monitoring, batch ops)
- **Phase 5 (v2):** Docker, VT100 emulation, plugins, web UI

## Commands
```bash
uv run tame                   # Run the app
uv run pytest                 # Run all tests
uv run pytest tests/ -x       # Stop on first failure
uv run pytest -k "pattern"    # Run specific tests
```

## Conventions
- Commit often with descriptive messages
- Keep main branch clean and running
- Tests for all core logic (session management, pattern matching, output buffer, notifications)
- No Docker in v1 — deferred to v2
- Notifications: notify-send for desktop, pygame/simpleaudio/bell fallback for audio
- Config: TOML with sensible defaults that work out of the box
- Status indicators: ● ACTIVE, ○ IDLE, ◉ WAITING, ✗ ERROR, ✓ DONE, ⏸ PAUSED

## Spec
Full technical specification: `docs/initial_specs.md`
