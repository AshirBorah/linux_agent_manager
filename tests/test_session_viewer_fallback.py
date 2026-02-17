from __future__ import annotations

from tame.ui.widgets.session_viewer import SessionViewer


def test_fallback_clear_sequence_drops_prior_content() -> None:
    existing = "line1\nline2\nline3\n"
    chunk = "\x1b[H\x1b[2J\x1b[3J$ "

    merged = SessionViewer._append_fallback_text(existing, chunk)

    assert "line1" not in merged
    assert "line2" not in merged
    assert merged.endswith("$ ")


def test_fallback_formfeed_clear_drops_prior_content() -> None:
    existing = "before clear"
    chunk = "\x0cafter clear"

    merged = SessionViewer._append_fallback_text(existing, chunk)

    assert merged == "after clear"


def test_fallback_home_then_j_clear_drops_prior_content() -> None:
    existing = "line before clear\n"
    chunk = "\x1b[H\x1b[Jprompt"

    merged = SessionViewer._append_fallback_text(existing, chunk)

    assert merged == "prompt"


def test_fallback_text_is_capped() -> None:
    max_chars = SessionViewer._FALLBACK_MAX_CHARS
    existing = "a" * max_chars
    chunk = "b" * 1024

    merged = SessionViewer._append_fallback_text(existing, chunk)

    assert len(merged) == max_chars
    assert merged.endswith("b" * 1024)


def test_show_snapshot_replaces_viewport_text() -> None:
    viewer = SessionViewer()
    viewer.show_snapshot("snapshot line\nnext")

    rendered = str(viewer.render())
    assert "snapshot line" in rendered
    assert "next" in rendered
