from __future__ import annotations

import textwrap

import pytest

from tame.config.defaults import DEFAULT_CONFIG
from tame.config.manager import ConfigManager


def test_default_config_has_all_sections() -> None:
    expected = {"general", "sessions", "patterns", "theme", "notifications", "keybindings"}
    assert expected == set(DEFAULT_CONFIG.keys())


def test_deep_merge_override() -> None:
    base = {"a": 1, "b": {"c": 2, "d": 3}}
    override = {"b": {"c": 99}}
    cm = ConfigManager.__new__(ConfigManager)
    result = cm._deep_merge(base, override)
    assert result["b"]["c"] == 99


def test_deep_merge_preserves_defaults() -> None:
    base = {"a": 1, "b": {"c": 2, "d": 3}}
    override = {"b": {"c": 99}}
    cm = ConfigManager.__new__(ConfigManager)
    result = cm._deep_merge(base, override)
    assert result["a"] == 1
    assert result["b"]["d"] == 3


def test_get_dot_path() -> None:
    cm = ConfigManager.__new__(ConfigManager)
    cm._config = {
        "sessions": {"idle_threshold_seconds": 300},
        "general": {"log_level": "INFO"},
    }
    assert cm.get("sessions.idle_threshold_seconds") == 300
    assert cm.get("general.log_level") == "INFO"


def test_get_missing_key_returns_default() -> None:
    cm = ConfigManager.__new__(ConfigManager)
    cm._config = {"general": {"log_level": "INFO"}}
    assert cm.get("general.nonexistent", "fallback") == "fallback"
    assert cm.get("no_section.no_key") is None


def test_load_creates_default_file(tmp_path: object) -> None:
    config_file = tmp_path / "tame" / "config.toml"  # type: ignore[operator]
    cm = ConfigManager(config_path=str(config_file))
    cfg = cm.load()

    assert config_file.exists()
    assert cfg["general"]["log_level"] == "INFO"
    assert cfg["sessions"]["idle_threshold_seconds"] == 300
    assert cfg["keybindings"]["quit"] == "f12"


def test_load_merges_user_config(tmp_path: object) -> None:
    config_file = tmp_path / "tame" / "config.toml"  # type: ignore[operator]
    config_file.parent.mkdir(parents=True, exist_ok=True)  # type: ignore[union-attr]
    config_file.write_text(  # type: ignore[union-attr]
        textwrap.dedent("""\
            [general]
            log_level = "DEBUG"
            max_buffer_lines = 5000

            [sessions]
            auto_resume = true
        """)
    )

    cm = ConfigManager(config_path=str(config_file))
    cfg = cm.load()

    # Overridden values
    assert cfg["general"]["log_level"] == "DEBUG"
    assert cfg["general"]["max_buffer_lines"] == 5000
    assert cfg["sessions"]["auto_resume"] is True

    # Preserved defaults
    assert cfg["general"]["state_file"] == "~/.local/share/tame/state.db"
    assert cfg["sessions"]["idle_threshold_seconds"] == 300
    assert "keybindings" in cfg
    assert cfg["keybindings"]["quit"] == "f12"


def test_default_config_error_has_shell_regexes() -> None:
    error_cfg = DEFAULT_CONFIG["patterns"]["error"]
    assert "shell_regexes" in error_cfg
    shell = error_cfg["shell_regexes"]
    assert isinstance(shell, list)
    assert len(shell) > 0
    assert r"command not found" in shell
