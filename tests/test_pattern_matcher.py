from __future__ import annotations

from lam.session.pattern_matcher import PatternMatcher

PATTERNS: dict[str, list[str]] = {
    "error": [
        r"(?i)\berror\b[:\s]",
        r"(?i)\bfatal\b[:\s]",
        r"Traceback \(most recent call last\)",
        r"(?i)APIError",
        r"(?i)rate.?limit(?:ed|ing)?(?:\s+(?:exceeded|reached|hit)|\s*[:\-])",
    ],
    "prompt": [
        r"\[y/n\]",
        r"\[Y/n\]",
        r"\[yes/no\]",
        r"(?i)approve|deny",
        r"\?\s*$",
    ],
    "completion": [
        r"(?i)\btask completed\b",
        r"(?i)\bdone\b",
        r"(?i)\bfinished\b",
    ],
    "progress": [
        r"\d+%",
        r"(?i)step\s+\d+\s*/\s*\d+",
    ],
}


def _matcher() -> PatternMatcher:
    return PatternMatcher(PATTERNS)


# ── Prompt detection ──────────────────────────────────────────────


def test_prompt_detection_yn() -> None:
    m = _matcher().scan("Continue? [y/n]")
    assert m is not None
    assert m.category == "prompt"


def test_prompt_detection_Yn() -> None:
    m = _matcher().scan("Proceed? [Y/n]")
    assert m is not None
    assert m.category == "prompt"


def test_prompt_detection_yes_no() -> None:
    m = _matcher().scan("Do you agree? [yes/no]")
    assert m is not None
    assert m.category == "prompt"


def test_prompt_detection_approve_deny() -> None:
    m = _matcher().scan("Please approve this action")
    assert m is not None
    assert m.category == "prompt"


def test_prompt_detection_question_mark() -> None:
    m = _matcher().scan("What is your name? ")
    assert m is not None
    assert m.category == "prompt"


# ── Error detection ───────────────────────────────────────────────


def test_error_detection_error_colon() -> None:
    m = _matcher().scan("error: something went wrong")
    assert m is not None
    assert m.category == "error"


def test_error_detection_fatal() -> None:
    m = _matcher().scan("fatal: not a git repository")
    assert m is not None
    assert m.category == "error"


def test_error_detection_traceback() -> None:
    m = _matcher().scan("Traceback (most recent call last)")
    assert m is not None
    assert m.category == "error"


def test_error_detection_api_error() -> None:
    m = _matcher().scan("Received APIError from provider")
    assert m is not None
    assert m.category == "error"


def test_error_detection_rate_limit() -> None:
    m = _matcher().scan("rate limit exceeded, please wait")
    assert m is not None
    assert m.category == "error"


def test_rate_limits_info_line_is_not_error() -> None:
    m = _matcher().scan("Tip: New 2x rate limits until April 2nd.")
    assert m is None


# ── Completion detection ──────────────────────────────────────────


def test_completion_detection_task_completed() -> None:
    m = _matcher().scan("Task completed successfully")
    assert m is not None
    assert m.category == "completion"


def test_completion_detection_done() -> None:
    m = _matcher().scan("Build done.")
    assert m is not None
    assert m.category == "completion"


def test_completion_detection_finished() -> None:
    m = _matcher().scan("Processing finished in 4.2s")
    assert m is not None
    assert m.category == "completion"


# ── Progress detection ────────────────────────────────────────────


def test_progress_detection_percentage() -> None:
    m = _matcher().scan("Downloading... 73%")
    assert m is not None
    assert m.category == "progress"
    assert m.matched_text == "73%"


def test_progress_detection_step_counter() -> None:
    m = _matcher().scan("step 3 / 10")
    assert m is not None
    assert m.category == "progress"


# ── Priority order ────────────────────────────────────────────────


def test_priority_order_error_before_prompt() -> None:
    # A line that matches both error and prompt should report error.
    m = _matcher().scan("error: approve this? [y/n]")
    assert m is not None
    assert m.category == "error"


# ── No match ──────────────────────────────────────────────────────


def test_no_match() -> None:
    m = _matcher().scan("just a normal output line")
    assert m is None
