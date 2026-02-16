from __future__ import annotations

from tame.session.output_buffer import OutputBuffer


def test_append_complete_lines() -> None:
    buf = OutputBuffer()
    buf.append_data("line one\nline two\n")
    assert buf.get_lines() == ["line one", "line two"]


def test_append_partial_lines() -> None:
    buf = OutputBuffer()
    buf.append_data("partial")
    assert buf.get_lines() == []
    assert buf.get_all_text() == "partial"

    buf.append_data(" end\n")
    assert buf.get_lines() == ["partial end"]


def test_ring_buffer_eviction() -> None:
    buf = OutputBuffer(maxlen=3)
    buf.append_data("a\nb\nc\nd\ne\n")
    lines = buf.get_lines()
    assert lines == ["c", "d", "e"]
    assert buf.total_lines_received == 5


def test_empty_buffer() -> None:
    buf = OutputBuffer()
    assert buf.get_lines() == []
    assert buf.get_all_text() == ""
    assert buf.total_lines_received == 0
    assert buf.total_bytes_received == 0


def test_multiline_append() -> None:
    buf = OutputBuffer()
    buf.append_data("alpha\nbeta\ngamma")
    assert buf.get_lines() == ["alpha", "beta"]
    assert buf.get_all_text() == "alpha\nbeta\ngamma"

    buf.append_data("\ndelta\n")
    assert buf.get_lines() == ["alpha", "beta", "gamma", "delta"]


def test_total_counters() -> None:
    buf = OutputBuffer()
    buf.append_data("hello\n")
    buf.append_data("world\n")
    assert buf.total_lines_received == 2
    assert buf.total_bytes_received == len("hello\n") + len("world\n")


def test_clear() -> None:
    buf = OutputBuffer()
    buf.append_data("some data\n")
    buf.clear()
    assert buf.get_lines() == []
    assert buf.get_all_text() == ""
    assert buf.total_lines_received == 0
    assert buf.total_bytes_received == 0
