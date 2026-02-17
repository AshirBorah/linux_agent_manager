from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

from tame.notifications.models import EventType, NotificationEvent, Priority
from tame.notifications.webhook import WebhookNotifier


def _make_event() -> NotificationEvent:
    return NotificationEvent(
        event_type=EventType.ERROR,
        session_id="s1",
        session_name="test-session",
        message="Something went wrong",
        priority=Priority.CRITICAL,
        matched_text="error: failed",
    )


def test_webhook_disabled_does_not_send() -> None:
    notifier = WebhookNotifier(enabled=False, url="http://example.com/hook")
    result = notifier.notify(_make_event())
    assert result is False


def test_webhook_empty_url_does_not_send() -> None:
    notifier = WebhookNotifier(enabled=True, url="")
    result = notifier.notify(_make_event())
    assert result is False


@patch("tame.notifications.webhook.urllib.request.urlopen")
def test_webhook_sends_json_payload(mock_urlopen: MagicMock) -> None:
    mock_urlopen.return_value = MagicMock()
    notifier = WebhookNotifier(enabled=True, url="http://example.com/hook")
    event = _make_event()
    result = notifier.notify(event)
    assert result is True
    mock_urlopen.assert_called_once()
    request = mock_urlopen.call_args[0][0]
    assert request.full_url == "http://example.com/hook"
    assert request.method == "POST"
    payload = json.loads(request.data)
    assert payload["event_type"] == "error"
    assert payload["session_id"] == "s1"
    assert payload["session_name"] == "test-session"


@patch("tame.notifications.webhook.urllib.request.urlopen")
def test_webhook_includes_custom_headers(mock_urlopen: MagicMock) -> None:
    mock_urlopen.return_value = MagicMock()
    notifier = WebhookNotifier(
        enabled=True,
        url="http://example.com/hook",
        headers={"Authorization": "Bearer tok123"},
    )
    notifier.notify(_make_event())
    request = mock_urlopen.call_args[0][0]
    assert request.get_header("Authorization") == "Bearer tok123"


@patch("tame.notifications.webhook.urllib.request.urlopen")
def test_webhook_handles_exception_gracefully(mock_urlopen: MagicMock) -> None:
    mock_urlopen.side_effect = Exception("Connection refused")
    notifier = WebhookNotifier(enabled=True, url="http://example.com/hook")
    result = notifier.notify(_make_event())
    assert result is False
