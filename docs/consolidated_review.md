# Consolidated Review — LAM Post-MVP

Three independent AI model reviews (GPT, Claude, Gemini) were conducted against the LAM codebase after MVP completion. This document consolidates their findings, separates signal from noise, and identifies actionable improvements.

## What the Reviews Got Right

### GPT Review (Most Actionable — All Claims Verified)

The GPT review was the most code-grounded and every claim was verified against the actual source:

- **WAITING state stuck after user sends input:** `send_input()` in `manager.py:165` updates `last_activity` but never clears the WAITING status. Sessions get permanently stuck in WAITING state after the user responds to a prompt.

- **IDLE state never triggers:** The `SessionState.IDLE` enum value exists and `idle_threshold_seconds` is defined in config defaults, but no code path ever sets a session to IDLE. The config value is completely unused.

- **Notification config schema mismatch:** `defaults.py` defines flat keys (`do_not_disturb`, `dnd_start`, `dnd_end`, `history_max`) but `NotificationEngine` reads nested keys via `config.get("dnd", {}).get("enabled")` and `config.get("history", {}).get("max_size")`. DND and history_max settings are silently ignored — they can never activate from config.

- **Keybindings hard-coded:** `LAMApp.BINDINGS` is a class-level constant. `KeybindManager` is instantiated with user config but never consulted at runtime. Changing keybindings in config has zero effect.

- **Weak patterns cause false positives:** `\?\s*$` matches any question in output. `\bdone\b` matches random log lines. `approve|deny` lacks word boundaries. These fire on normal output, not just interactive prompts.

- **`idle_prompt_timeout` unused:** Value `3.0` exists in config but no code references it. It was intended to gate weak patterns but was never implemented.

- **Matched text not in notifications:** `_handle_status_change` calls `dispatch()` without passing the matched text. Users see "Session X is WAITING" but never see *what* triggered it.

- **Pattern duplication:** `SessionManager.DEFAULT_PATTERNS` (manager.py:18-42) and `defaults.py` patterns config contain different regexes for the same purpose — two sources of truth.

- **Missing theme files:** Only `dark.tcss` and `light.tcss` exist. The 6 other advertised themes (dracula, nord, monokai, gruvbox, solarized_dark, solarized_light) are missing.

### Claude Review (Meta-Review)

The Claude review served as a meta-analysis of the other two reviews:

- Correctly identified that the Gemini review hallucinated the project scope
- Validated the GPT analysis findings and core architecture soundness
- Noted resource monitoring is already in the roadmap (`psutil` dependency exists, not wired)

### Gemini Review (Mostly Hallucinated — Salvageable Parts Only)

The Gemini review fundamentally misunderstood the project:

- Described LAM as a headless daemon supervisor (wrong — it's an interactive TUI)
- Recommended systemd integration for PTY shells (nonsensical for TUI app)
- Suggested multi-server SSH orchestration (scope explosion)

**Salvageable ideas:**
- Unread/attention badges on sidebar items for non-active sessions
- Smart scroll behavior (lock-to-bottom with scroll-up detection)

## What to Ignore

- **Gemini's entire framing** — daemon supervisor, headless management, systemd integration
- **SQLite persistence urgency** — tmux-first stance is correct; defer native persistence
- **Web UI / orchestration layer** — v2 scope, out of bounds for post-MVP
- **Full VT100 emulation push** — pyte is already integrated and sufficient for v1
- **Auto-rename sessions via API** — users name sessions on creation; rename capability is sufficient

## Consensus Across Reviews

All three reviews agree on the fundamental assessment:

> **Core architecture (PTY + asyncio + epoll) is solid.** The friction is about **trust** (status correctness) and **config alignment** (settings that don't work), not missing features.

The primary issues are:
1. **State machine correctness** — states get stuck, transitions missing, single enum conflates process lifecycle with attention state
2. **Config-code alignment** — settings exist in config that have zero effect at runtime
3. **Pattern precision** — weak patterns fire too aggressively without timeout gating
4. **Visual completeness** — advertised themes don't exist, search doesn't work

## Priority Classification

| Priority | Category | Issues |
|----------|----------|--------|
| **P0** | Bugs (config/code mismatches) | Notification schema, pattern duplication, keybind wiring |
| **P1** | Trust & Reliability | State refactor, WAITING fix, IDLE detection, pattern gating, pattern tightening, matched text in notifications |
| **P1** | Trust & Reliability (patterns) | Tighten defaults, include matched text |
| **P2** | UX Enhancements | Sidebar search, attention badges, smart scroll, session rename |
| **P2** | Theme & Visual | Generate missing themes, runtime theme switching |
| **P3** | Infrastructure & Polish | CI pipeline, resource monitoring, README/config cleanup |
