from __future__ import annotations

from unittest.mock import patch

from tame.notifications.desktop import DesktopNotifier
from tame.notifications.models import EventType, NotificationEvent, Priority


def _make_event(**kwargs) -> NotificationEvent:
    defaults = {
        "event_type": EventType.ERROR,
        "session_id": "s1",
        "session_name": "agent-1",
        "message": "something broke",
        "priority": Priority.CRITICAL,
    }
    defaults.update(kwargs)
    return NotificationEvent(**defaults)


class TestDesktopNotifier:
    def test_is_available_true(self) -> None:
        notifier = DesktopNotifier()
        with patch("shutil.which", return_value="/usr/bin/notify-send"):
            assert notifier.is_available() is True

    def test_is_available_false(self) -> None:
        notifier = DesktopNotifier()
        with patch("shutil.which", return_value=None):
            assert notifier.is_available() is False

    def test_notify_calls_subprocess(self) -> None:
        notifier = DesktopNotifier(timeout_ms=3000)
        event = _make_event()

        with (
            patch.object(notifier, "is_available", return_value=True),
            patch("tame.notifications.desktop.subprocess.Popen") as mock_popen,
        ):
            notifier.notify(event)

        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == "notify-send"
        assert "--urgency" in cmd
        assert "critical" in cmd
        assert "TAME: agent-1" in cmd
        assert "something broke" in cmd

    def test_disabled_does_nothing(self) -> None:
        notifier = DesktopNotifier(enabled=False)
        event = _make_event()

        with patch("tame.notifications.desktop.subprocess.Popen") as mock_popen:
            notifier.notify(event)

        mock_popen.assert_not_called()
