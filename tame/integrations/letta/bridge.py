from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from .client import LettaClient

log = logging.getLogger("tame.letta")


class MemoryBridge:
    """Bridge between TAME session events and Letta's memory agent.

    All public methods are safe to call regardless of connection state —
    they silently no-op when the bridge is disabled or disconnected.
    """

    def __init__(self, server_url: str = "http://localhost:8283") -> None:
        self._client = LettaClient(server_url)
        self._enabled = False
        self._server_url = server_url

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    @property
    def status(self) -> str:
        """Return a status string for the status bar."""
        if not self._enabled:
            return "off"
        if self._client.is_connected:
            return "on"
        return "err"

    def enable(self) -> tuple[bool, str]:
        """Try to connect and enable the bridge.

        Returns (success, message).
        """
        if self._client.connect():
            self._enabled = True
            return True, "Memory enabled. Session events will be recorded."
        return False, (
            f"Letta server not found at {self._server_url}. "
            "Run 'letta server' in another terminal, then try again."
        )

    def disable(self) -> None:
        """Pause recording (keeps connection alive for queries)."""
        self._enabled = False

    def toggle(self) -> tuple[bool, str]:
        """Toggle the bridge on/off. Returns (new_enabled_state, message)."""
        if self._enabled:
            self.disable()
            return False, "Memory paused"
        return self.enable()

    # ------------------------------------------------------------------
    # Event recording (called from app/session hooks)
    # ------------------------------------------------------------------

    def record_session_created(self, name: str, working_dir: str) -> None:
        if not self._enabled or not self._client.is_connected:
            return
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        self._send_async(
            f"[EVENT] Session '{name}' created at {ts}. "
            f"Working directory: {working_dir}"
        )

    def record_session_ended(
        self, name: str, exit_code: int | None, duration_seconds: float
    ) -> None:
        if not self._enabled or not self._client.is_connected:
            return
        mins = duration_seconds / 60
        self._send_async(
            f"[EVENT] Session '{name}' ended with exit code {exit_code} "
            f"after {mins:.1f} minutes."
        )

    def record_error(self, name: str, error_text: str) -> None:
        if not self._enabled or not self._client.is_connected:
            return
        self._send_async(f"[EVENT] Error in session '{name}': {error_text[:500]}")

    def record_status_change(
        self, name: str, old_state: str, new_state: str, matched_text: str
    ) -> None:
        if not self._enabled or not self._client.is_connected:
            return
        msg = f"[EVENT] Session '{name}' changed from {old_state} to {new_state}."
        if matched_text:
            msg += f" Matched: {matched_text[:200]}"
        self._send_async(msg)

    # ------------------------------------------------------------------
    # Querying (works even when recording is paused)
    # ------------------------------------------------------------------

    async def query(self, question: str) -> str:
        """Ask the memory agent a question. Returns the response text."""
        if not self._client.is_connected:
            return "Memory is not connected. Enable memory first."
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._client.send_message, question)

    # ------------------------------------------------------------------
    # Memory management
    # ------------------------------------------------------------------

    async def clear(self) -> tuple[bool, str]:
        """Clear all memory. Returns (success, message)."""
        if not self._client.is_connected:
            return False, "Memory is not connected."
        loop = asyncio.get_running_loop()
        success = await loop.run_in_executor(None, self._client.clear_memory)
        if success:
            return True, "All session memory cleared."
        return False, "Failed to clear memory."

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _send_async(self, text: str) -> None:
        """Fire-and-forget message send to Letta (non-blocking)."""
        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, self._client.send_message, text)
        except RuntimeError:
            pass
