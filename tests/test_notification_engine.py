from __future__ import annotations

from unittest.mock import MagicMock

from tame.notifications.engine import NotificationEngine
from tame.notifications.models import EVENT_PRIORITY, EventType, Priority


def _make_engine(config: dict | None = None) -> NotificationEngine:
    if config is None:
        config = {"desktop": {"enabled": False}, "audio": {"enabled": False}}
    return NotificationEngine(config)


class TestDispatch:
    def test_dispatch_creates_event(self) -> None:
        engine = _make_engine()
        event = engine.dispatch(
            event_type=EventType.ERROR,
            session_id="s1",
            session_name="agent-1",
            message="segfault",
            matched_text="Segmentation fault",
        )

        assert event.event_type is EventType.ERROR
        assert event.session_id == "s1"
        assert event.session_name == "agent-1"
        assert event.message == "segfault"
        assert event.matched_text == "Segmentation fault"
        assert event.priority is Priority.CRITICAL

    def test_dnd_suppresses_notifications(self) -> None:
        engine = _make_engine(
            {
                "desktop": {"enabled": True},
                "audio": {"enabled": True},
            }
        )
        engine.set_dnd(True)

        toast_cb = MagicMock()
        engine.on_toast = toast_cb

        engine.dispatch(
            event_type=EventType.ERROR,
            session_id="s1",
            session_name="agent-1",
            message="boom",
        )

        toast_cb.assert_not_called()

    def test_routing_respects_config(self) -> None:
        engine = _make_engine(
            {
                "desktop": {"enabled": True},
                "audio": {"enabled": True},
            }
        )

        toast_cb = MagicMock()
        sidebar_cb = MagicMock()
        engine.on_toast = toast_cb
        engine.on_sidebar_flash = sidebar_cb

        # session_idle default routing: desktop=False, audio=False,
        # toast=True, sidebar_flash=False
        engine.dispatch(
            event_type=EventType.SESSION_IDLE,
            session_id="s2",
            session_name="agent-2",
            message="idle",
        )

        toast_cb.assert_called_once()
        sidebar_cb.assert_not_called()

    def test_history_records_events(self) -> None:
        engine = _make_engine()

        engine.dispatch(
            event_type=EventType.COMPLETED,
            session_id="s1",
            session_name="agent-1",
            message="done",
        )
        engine.dispatch(
            event_type=EventType.ERROR,
            session_id="s2",
            session_name="agent-2",
            message="fail",
        )

        history = engine.get_history()
        assert len(history) == 2

        recent = history.get_recent(1)
        assert len(recent) == 1
        assert recent[0].event_type is EventType.ERROR

    def test_history_ring_buffer_eviction(self) -> None:
        engine = _make_engine(
            {
                "desktop": {"enabled": False},
                "audio": {"enabled": False},
                "history": {"max_size": 3},
            }
        )

        for i in range(5):
            engine.dispatch(
                event_type=EventType.COMPLETED,
                session_id=f"s{i}",
                session_name=f"agent-{i}",
                message=f"msg-{i}",
            )

        history = engine.get_history()
        assert len(history) == 3

        all_events = history.get_all()
        assert all_events[0].session_id == "s2"
        assert all_events[-1].session_id == "s4"

    def test_priority_mapping(self) -> None:
        assert EVENT_PRIORITY[EventType.INPUT_NEEDED] is Priority.HIGH
        assert EVENT_PRIORITY[EventType.ERROR] is Priority.CRITICAL
        assert EVENT_PRIORITY[EventType.COMPLETED] is Priority.MEDIUM
        assert EVENT_PRIORITY[EventType.SESSION_IDLE] is Priority.LOW

    def test_dnd_from_config(self) -> None:
        config = {
            "dnd": {"enabled": True, "start": "22:00", "end": "07:00"},
            "history": {"max_size": 100},
            "desktop": {"enabled": False},
            "audio": {"enabled": False},
        }
        engine = NotificationEngine(config)
        assert engine._dnd_enabled is True
        assert engine._dnd_start is not None
        assert engine._dnd_end is not None
        assert engine._history._events.maxlen == 100
