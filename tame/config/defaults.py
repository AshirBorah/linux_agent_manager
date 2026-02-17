from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def get_profile_patterns(profile: str) -> dict[str, list[str]]:
    """Get extra patterns for a named profile.

    Returns a dict of ``{category: [regex, ...]}`` to merge with base
    patterns.  Returns empty dict if *profile* is empty or unknown.
    """
    if not profile:
        return {}
    profiles = DEFAULT_CONFIG.get("profiles", {})
    profile_cfg = profiles.get(profile)
    if profile_cfg is None:
        log.warning("Unknown pattern profile %r", profile)
        return {}
    result: dict[str, list[str]] = {}
    for category, cat_cfg in profile_cfg.items():
        if isinstance(cat_cfg, dict) and "regexes" in cat_cfg:
            result[category] = list(cat_cfg["regexes"])
    return result


def get_default_patterns_flat() -> dict[str, list[str]]:
    """Flatten structured config patterns into {category: [regex, ...]}."""
    patterns_cfg = DEFAULT_CONFIG["patterns"]
    result: dict[str, list[str]] = {}
    for category in ("error", "prompt", "completion", "progress"):
        cat_cfg = patterns_cfg.get(category, {})
        if isinstance(cat_cfg, dict):
            regexes = list(cat_cfg.get("regexes", []))
            shell_regexes = list(cat_cfg.get("shell_regexes", []))
            result[category] = regexes + shell_regexes
    # Expose weak prompt patterns separately for timeout gating
    prompt_cfg = patterns_cfg.get("prompt", {})
    if isinstance(prompt_cfg, dict):
        result["weak_prompt"] = list(prompt_cfg.get("weak_regexes", []))
    return result


DEFAULT_CONFIG: dict = {
    "general": {
        "log_file": "~/.local/share/tame/tame.log",
        "log_level": "INFO",
        "max_buffer_lines": 10000,
    },
    "sessions": {
        "auto_resume": False,
        "default_working_directory": "",
        "default_shell": "",
        "start_in_tmux": True,
        "restore_tmux_sessions_on_startup": True,
        "tmux_session_prefix": "tame",
        "max_concurrent_sessions": 0,
        "idle_threshold_seconds": 300,
        "resource_poll_seconds": 5,
    },
    "patterns": {
        "prompt": {
            "regexes": [
                r"\[y/n\]",
                r"\[Y/n\]",
                r"\[yes/no\]",
                r"\(a\)pprove.*\(d\)eny",
                r"Do you want to (?:continue|proceed)",
                r"Press [Ee]nter to continue",
                r"Allow .+ to .+\?",
            ],
            "weak_regexes": [
                r"\?\s*$",
            ],
            "shell_regexes": [],
        },
        "error": {
            "regexes": [
                r"(?i)\berror\b\s*:",
                r"(?i)\bfatal\b\s*:",
                r"Traceback \(most recent call last\)",
                r"(?i)\bAPIError\b",
                r"(?i)rate.?limit(?:ed|ing)?(?:\s+(?:exceeded|reached|hit)|\s*[:\-])",
            ],
            "shell_regexes": [
                r"command not found",
                r"No such file or directory",
                r"Permission denied",
                r"(?i)segmentation fault",
            ],
        },
        "completion": {
            "regexes": [
                r"(?i)^\s*task\s+completed\.?\s*$",
                r"(?i)^\s*all\s+tasks?\s+(?:completed|done)\.?\s*$",
            ],
            "shell_regexes": [],
        },
        "progress": {
            "regexes": [
                r"\b\d{1,3}%",
                r"Step \d+/\d+",
            ],
            "shell_regexes": [],
        },
        "idle_prompt_timeout": 3.0,
        "state_debounce_ms": 500,
    },
    "theme": {
        "current": "dark",
        "custom_css_path": "",
        "colors": {},
        "borders": {},
    },
    "notifications": {
        "enabled": True,
        "dnd": {
            "enabled": False,
            "start": "",
            "end": "",
        },
        "history": {
            "max_size": 500,
        },
        "desktop": {
            "enabled": True,
            "urgency": "normal",
            "icon_path": "",
            "timeout_ms": 5000,
        },
        "audio": {
            "enabled": True,
            "volume": 0.7,
            "backend_preference": ["pygame", "simpleaudio", "bell"],
            "sounds": {
                "input_needed": "",
                "error": "",
                "completed": "",
                "default": "",
            },
        },
        "slack": {
            "enabled": False,
            "webhook_url": "",
            "verbosity": 10,
            "sessions": [],
        },
        "webhook": {
            "enabled": False,
            "url": "",
            "headers": {},
            "timeout": 5.0,
        },
        "toast": {
            "enabled": True,
            "display_seconds": 5,
            "max_visible": 3,
        },
        "routing": {
            "input_needed": {
                "priority": "high",
                "desktop": True,
                "audio": True,
                "toast": True,
                "sidebar_flash": True,
            },
            "error": {
                "priority": "critical",
                "desktop": True,
                "audio": True,
                "toast": True,
                "sidebar_flash": True,
            },
            "completed": {
                "priority": "medium",
                "desktop": True,
                "audio": True,
                "toast": True,
                "sidebar_flash": False,
            },
            "session_idle": {
                "priority": "low",
                "desktop": False,
                "audio": False,
                "toast": True,
                "sidebar_flash": False,
            },
        },
    },
    "profiles": {
        "claude": {
            "prompt": {
                "regexes": [
                    r"\(a\)pprove.*\(d\)eny",
                    r"Allow .+ to .+\?",
                    r"Do you want to (?:continue|proceed)",
                ],
            },
            "error": {
                "regexes": [
                    r"(?i)\bAPIError\b",
                    r"(?i)rate.?limit(?:ed|ing)?(?:\s+(?:exceeded|reached|hit)|\s*[:\-])",
                    r"(?i)\bmax\s+tool\s+use\b",
                ],
            },
        },
        "codex": {
            "prompt": {
                "regexes": [
                    r"\[y/n\]",
                    r"Do you want to (?:continue|proceed)",
                ],
            },
            "error": {
                "regexes": [
                    r"(?i)\bAPIError\b",
                    r"(?i)rate.?limit(?:ed|ing)?(?:\s+(?:exceeded|reached|hit)|\s*[:\-])",
                ],
            },
        },
        "training": {
            "progress": {
                "regexes": [
                    r"(?i)\bepoch\s+\d+",
                    r"(?i)\bloss\s*[:=]\s*[\d.]+",
                    r"\b\d{1,3}%",
                    r"Step \d+/\d+",
                ],
            },
            "completion": {
                "regexes": [
                    r"(?i)training\s+(?:complete|finished|done)",
                ],
            },
            "error": {
                "regexes": [
                    r"(?i)\bOOM\b",
                    r"(?i)CUDA\s+out\s+of\s+memory",
                    r"(?i)\bnan\s+loss\b",
                ],
            },
        },
    },
    "keybindings": {
        "new_session": "f2",
        "rename_session": "f9",
        "prev_session": "f3",
        "next_session": "f4",
        "toggle_sidebar": "f6",
        "resume_all": "f7",
        "pause_all": "f8",
        "show_diff": "f10",
        "set_group": "f11",
        "quit": "f12",
        "session_1": "alt+1",
        "session_2": "alt+2",
        "session_3": "alt+3",
        "session_4": "alt+4",
        "session_5": "alt+5",
        "session_6": "alt+6",
        "session_7": "alt+7",
        "session_8": "alt+8",
        "session_9": "alt+9",
    },
}
