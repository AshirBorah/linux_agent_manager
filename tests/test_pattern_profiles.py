from __future__ import annotations

from tame.config.defaults import get_profile_patterns, DEFAULT_CONFIG
from tame.session.pattern_matcher import PatternMatcher


# ------------------------------------------------------------------
# Profile lookup
# ------------------------------------------------------------------


def test_get_claude_profile_has_prompt() -> None:
    patterns = get_profile_patterns("claude")
    assert "prompt" in patterns
    assert len(patterns["prompt"]) > 0


def test_get_codex_profile_has_prompt() -> None:
    patterns = get_profile_patterns("codex")
    assert "prompt" in patterns


def test_get_training_profile_has_progress() -> None:
    patterns = get_profile_patterns("training")
    assert "progress" in patterns
    assert any("epoch" in r.lower() for r in patterns["progress"])


def test_unknown_profile_returns_empty() -> None:
    patterns = get_profile_patterns("nonexistent")
    assert patterns == {}


def test_empty_profile_returns_empty() -> None:
    patterns = get_profile_patterns("")
    assert patterns == {}


# ------------------------------------------------------------------
# Profile pattern merging
# ------------------------------------------------------------------


def test_claude_profile_detects_approve_deny() -> None:
    """Claude profile should detect the approve/deny prompt."""
    base = {"prompt": [r"\[y/n\]"]}
    profile = get_profile_patterns("claude")
    merged: dict[str, list[str]] = {}
    for cat in set(list(base) + list(profile)):
        merged[cat] = list(profile.get(cat, [])) + list(base.get(cat, []))
    matcher = PatternMatcher(merged)
    m = matcher.scan("(a)pprove or (d)eny")
    assert m is not None
    assert m.category == "prompt"


def test_training_profile_detects_epoch() -> None:
    """Training profile should detect epoch progress lines."""
    profile = get_profile_patterns("training")
    matcher = PatternMatcher(profile)
    m = matcher.scan("Epoch 5/100 - loss: 0.42")
    assert m is not None
    assert m.category == "progress"


def test_training_profile_detects_oom() -> None:
    """Training profile should detect CUDA OOM errors."""
    profile = get_profile_patterns("training")
    matcher = PatternMatcher(profile)
    m = matcher.scan("CUDA out of memory. Tried to allocate 2.00 GiB")
    assert m is not None
    assert m.category == "error"


# ------------------------------------------------------------------
# Profile config structure
# ------------------------------------------------------------------


def test_profiles_section_exists_in_defaults() -> None:
    assert "profiles" in DEFAULT_CONFIG


def test_all_profiles_have_valid_structure() -> None:
    profiles = DEFAULT_CONFIG["profiles"]
    for name, profile_cfg in profiles.items():
        assert isinstance(profile_cfg, dict), f"Profile {name} is not a dict"
        for cat, cat_cfg in profile_cfg.items():
            assert isinstance(cat_cfg, dict), f"{name}.{cat} is not a dict"
            assert "regexes" in cat_cfg, f"{name}.{cat} missing 'regexes'"
            assert isinstance(cat_cfg["regexes"], list), f"{name}.{cat}.regexes not list"
