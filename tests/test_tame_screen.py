"""Tests for TAMEScreen alternate screen buffer support."""

from __future__ import annotations

import pyte

from tame.ui.widgets.session_viewer import TAMEScreen


def _make_screen(cols: int = 80, lines: int = 24) -> tuple[TAMEScreen, pyte.Stream]:
    screen = TAMEScreen(columns=cols, lines=lines, history=100)
    stream = pyte.Stream(screen)
    return screen, stream


def _read_line(screen: TAMEScreen, y: int) -> str:
    """Read a full row from the screen buffer as a string (trailing spaces stripped)."""
    row = screen.buffer.get(y, {})
    chars = []
    for x in range(screen.columns):
        char = row.get(x)
        chars.append(" " if char is None else (char.data or " "))
    return "".join(chars).rstrip()


def test_enter_and_exit_alt_screen_restores_buffer() -> None:
    """Content written before alt screen should be restored after exit."""
    screen, stream = _make_screen(cols=40, lines=5)

    # Write to main buffer
    stream.feed("Hello, main buffer!")

    main_line = _read_line(screen, 0)
    assert "Hello, main buffer!" in main_line

    # Enter alt screen (mode 1049)
    stream.feed("\x1b[?1049h")

    # Main buffer content should be gone (alt screen is blank)
    alt_line = _read_line(screen, 0)
    assert "Hello, main buffer!" not in alt_line

    # Write in alt screen
    stream.feed("Alt screen content")
    assert "Alt screen content" in _read_line(screen, 0)

    # Exit alt screen
    stream.feed("\x1b[?1049l")

    # Main buffer should be restored
    restored = _read_line(screen, 0)
    assert "Hello, main buffer!" in restored
    # Alt content should be gone
    assert "Alt screen content" not in restored


def test_mode_1047_works() -> None:
    """Mode 1047 should also trigger alt screen (without cursor save)."""
    screen, stream = _make_screen(cols=40, lines=5)

    stream.feed("Original content")
    stream.feed("\x1b[?1047h")

    assert "Original content" not in _read_line(screen, 0)

    stream.feed("Temporary")
    stream.feed("\x1b[?1047l")

    assert "Original content" in _read_line(screen, 0)


def test_cursor_saved_with_1049() -> None:
    """Mode 1049 should save and restore cursor position."""
    screen, stream = _make_screen(cols=40, lines=5)

    stream.feed("ABCDE")
    cursor_x_before = screen.cursor.x

    stream.feed("\x1b[?1049h")
    # Cursor should reset in alt screen
    assert screen.cursor.x == 0
    assert screen.cursor.y == 0

    stream.feed("XYZ")

    stream.feed("\x1b[?1049l")
    assert screen.cursor.x == cursor_x_before


def test_double_enter_is_noop() -> None:
    """Entering alt screen twice should not clobber the saved buffer."""
    screen, stream = _make_screen(cols=40, lines=5)

    stream.feed("Important data")
    stream.feed("\x1b[?1049h")
    stream.feed("First alt write")
    # Second enter should be a no-op
    stream.feed("\x1b[?1049h")
    stream.feed("Second alt write")

    stream.feed("\x1b[?1049l")
    assert "Important data" in _read_line(screen, 0)


def test_exit_without_enter_is_noop() -> None:
    """Exiting alt screen without entering should not corrupt the buffer."""
    screen, stream = _make_screen(cols=40, lines=5)

    stream.feed("Normal content")
    stream.feed("\x1b[?1049l")  # exit without enter

    assert "Normal content" in _read_line(screen, 0)


def test_dirty_lines_marked_on_enter_and_exit() -> None:
    """All lines should be marked dirty on enter and exit."""
    screen, stream = _make_screen(cols=40, lines=5)

    stream.feed("text")
    screen.dirty.clear()

    stream.feed("\x1b[?1049h")
    assert screen.dirty == set(range(5))

    screen.dirty.clear()
    stream.feed("\x1b[?1049l")
    assert screen.dirty == set(range(5))


def test_other_private_modes_still_work() -> None:
    """Non-alt-screen private modes should pass through to pyte."""
    screen, stream = _make_screen(cols=40, lines=5)

    # DECTCEM: hide cursor (mode 25)
    stream.feed("\x1b[?25l")
    assert screen.cursor.hidden

    stream.feed("\x1b[?25h")
    assert not screen.cursor.hidden


def test_mode_47_works() -> None:
    """Legacy mode 47 should also trigger alt screen (swap only, no cursor save)."""
    screen, stream = _make_screen(cols=40, lines=5)

    stream.feed("Legacy content")
    stream.feed("\x1b[?47h")

    assert "Legacy content" not in _read_line(screen, 0)

    stream.feed("Temp stuff")
    stream.feed("\x1b[?47l")

    assert "Legacy content" in _read_line(screen, 0)


def test_mode_1048_cursor_only() -> None:
    """Mode 1048 saves/restores cursor without swapping buffers."""
    screen, stream = _make_screen(cols=40, lines=5)

    stream.feed("Hello")
    cursor_x = screen.cursor.x

    # Save cursor only
    stream.feed("\x1b[?1048h")
    # Content should still be visible (no buffer swap)
    assert "Hello" in _read_line(screen, 0)

    stream.feed("\x1b[2;1H")  # move cursor to row 2, col 1
    assert screen.cursor.y == 1

    # Restore cursor only
    stream.feed("\x1b[?1048l")
    assert screen.cursor.x == cursor_x
    assert screen.cursor.y == 0


def test_alt_screen_buffer_is_different_object() -> None:
    """Entering alt screen should swap to a distinct buffer object."""
    screen, stream = _make_screen(cols=40, lines=5)

    main_buffer = screen.buffer
    stream.feed("\x1b[?1049h")
    alt_buffer = screen.buffer

    # Must be different objects — true isolation
    assert alt_buffer is not main_buffer

    stream.feed("\x1b[?1049l")
    # After exit, we should be back to the original main buffer
    assert screen.buffer is main_buffer


def test_resize_during_alt_screen_clips_saved_buffer() -> None:
    """Shrinking columns during alt screen should clip saved main buffer."""
    screen, stream = _make_screen(cols=40, lines=5)

    # Write a long line in the main buffer
    stream.feed("A" * 40)
    assert _read_line(screen, 0) == "A" * 40

    # Enter alt screen
    stream.feed("\x1b[?1049h")

    # Shrink columns — saved main buffer should be clipped
    screen.resize(lines=5, columns=20)

    # Exit alt screen
    stream.feed("\x1b[?1049l")

    # Main buffer should only have 20 columns worth of data
    restored = _read_line(screen, 0)
    assert len(restored) <= 20


def test_resize_during_alt_screen_widens_ok() -> None:
    """Growing columns during alt screen should preserve main buffer content."""
    screen, stream = _make_screen(cols=20, lines=5)

    stream.feed("Hello World!")
    assert "Hello World!" in _read_line(screen, 0)

    # Enter alt screen
    stream.feed("\x1b[?1049h")

    # Widen columns — saved buffer content should be preserved
    screen.resize(lines=5, columns=40)

    # Exit alt screen
    stream.feed("\x1b[?1049l")

    assert "Hello World!" in _read_line(screen, 0)


def test_resize_not_in_alt_screen_no_error() -> None:
    """Resizing outside alt screen should work without errors."""
    screen, stream = _make_screen(cols=40, lines=5)

    stream.feed("Some content")
    assert "Some content" in _read_line(screen, 0)

    # Resize without alt screen active — should not raise
    screen.resize(lines=10, columns=60)

    # Content should still be accessible (pyte may reflow)
    # Just verify no exception was raised and screen is usable
    assert screen.columns == 60
    assert screen.lines == 10
