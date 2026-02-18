from __future__ import annotations

import asyncio
import importlib
import logging
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

log = logging.getLogger("tame.letta")

# Maximum seconds to wait for the Letta server to become ready.
_SERVER_STARTUP_TIMEOUT = 30


def _is_letta_installed() -> bool:
    """Check if letta-client is importable."""
    try:
        importlib.import_module("letta_client")
        return True
    except ImportError:
        return False


def _install_letta() -> tuple[bool, str]:
    """Install letta-client via uv into the current environment.

    Returns (success, message).
    """
    uv = shutil.which("uv")
    if uv is None:
        return False, "uv not found. Run: uv pip install letta-client"
    try:
        proc = subprocess.run(
            [uv, "pip", "install", "letta-client"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.strip()
            log.warning("Failed to install letta-client: %s", stderr)
            return False, f"Install failed: {stderr[:200]}"
        # Force Python to re-scan site-packages so the new package is importable.
        importlib.invalidate_caches()
        return True, "letta-client installed."
    except Exception as exc:
        log.exception("Error installing letta-client")
        return False, f"Install error: {exc}"


def _start_letta_server() -> subprocess.Popen | None:
    """Start ``letta server`` as a background process.

    Returns the Popen handle, or None on failure.
    """
    letta_bin = shutil.which("letta")
    if letta_bin is None:
        # After a fresh install the PATH entry for the venv Scripts/bin dir
        # is already present — but ``shutil.which`` may not find a brand-new
        # entry.  Fall back to invoking via ``python -m letta``.
        letta_bin = None

    try:
        if letta_bin:
            cmd = [letta_bin, "server"]
        else:
            cmd = [sys.executable, "-m", "letta", "server"]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc
    except Exception:
        log.exception("Failed to start letta server")
        return None


def _wait_for_server(url: str, timeout: float = _SERVER_STARTUP_TIMEOUT) -> bool:
    """Poll the Letta server health endpoint until it responds."""
    import urllib.request
    import urllib.error

    health_url = f"{url}/v1/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(health_url, method="GET")
            with urllib.request.urlopen(req, timeout=2):
                return True
        except Exception:
            time.sleep(0.5)
    return False


class MemoryBridge:
    """Bridge between TAME session events and Letta's memory agent.

    All public methods are safe to call regardless of connection state —
    they silently no-op when the bridge is disabled or disconnected.
    """

    def __init__(self, server_url: str = "http://localhost:8283") -> None:
        self._client = None  # LettaClient, created after install
        self._enabled = False
        self._server_url = server_url
        self._server_proc: subprocess.Popen | None = None

        # Eagerly create client if letta-client is already installed.
        if _is_letta_installed():
            from .client import LettaClient

            self._client = LettaClient(server_url)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    @property
    def status(self) -> str:
        """Return a status string for the status bar."""
        if not self._enabled:
            return "off"
        if self.is_connected:
            return "on"
        return "err"

    # ------------------------------------------------------------------
    # Full auto-setup: install → start server → connect
    # ------------------------------------------------------------------

    def setup(self) -> tuple[bool, str]:
        """Install letta-client if needed, start the server, and connect.

        This is a blocking call meant to be run in an executor.
        Returns (success, message).
        """
        # Step 1: install if missing
        if not _is_letta_installed():
            log.info("Installing letta-client...")
            ok, msg = _install_letta()
            if not ok:
                return False, msg
            # Verify import works after install
            if not _is_letta_installed():
                return False, (
                    "letta-client was installed but cannot be imported. "
                    "Restart TAME and try again."
                )

        # Step 2: create client if we haven't yet
        if self._client is None:
            from .client import LettaClient

            self._client = LettaClient(self._server_url)

        # Step 3: try connecting (server may already be running)
        if self._client.connect():
            self._enabled = True
            return True, "Memory enabled."

        # Step 4: server not running — start it
        log.info("Starting Letta server...")
        self._server_proc = _start_letta_server()
        if self._server_proc is None:
            return False, "Failed to start Letta server."

        # Step 5: wait for server to be ready
        if not _wait_for_server(self._server_url):
            self.stop_server()
            return False, (
                "Letta server started but did not become ready "
                f"within {_SERVER_STARTUP_TIMEOUT}s."
            )

        # Step 6: connect
        if self._client.connect():
            self._enabled = True
            return True, "Memory enabled."

        return False, "Server is running but connection failed."

    # ------------------------------------------------------------------
    # Simple enable/disable (assumes letta-client is already installed)
    # ------------------------------------------------------------------

    def enable(self) -> tuple[bool, str]:
        """Try to connect and enable the bridge.

        Returns (success, message).
        """
        if self._client is None:
            if not _is_letta_installed():
                return False, "letta-client is not installed."
            from .client import LettaClient

            self._client = LettaClient(self._server_url)

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
    # Server lifecycle
    # ------------------------------------------------------------------

    def stop_server(self) -> None:
        """Stop the Letta server if we started it."""
        if self._server_proc is not None:
            try:
                self._server_proc.terminate()
                self._server_proc.wait(timeout=5)
            except Exception:
                try:
                    self._server_proc.kill()
                except Exception:
                    pass
            self._server_proc = None
            log.info("Letta server stopped.")

    # ------------------------------------------------------------------
    # Event recording (called from app/session hooks)
    # ------------------------------------------------------------------

    def record_session_created(self, name: str, working_dir: str) -> None:
        if not self._enabled or not self.is_connected:
            return
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        self._send_async(
            f"[EVENT] Session '{name}' created at {ts}. "
            f"Working directory: {working_dir}"
        )

    def record_session_ended(
        self, name: str, exit_code: int | None, duration_seconds: float
    ) -> None:
        if not self._enabled or not self.is_connected:
            return
        mins = duration_seconds / 60
        self._send_async(
            f"[EVENT] Session '{name}' ended with exit code {exit_code} "
            f"after {mins:.1f} minutes."
        )

    def record_error(self, name: str, error_text: str) -> None:
        if not self._enabled or not self.is_connected:
            return
        self._send_async(f"[EVENT] Error in session '{name}': {error_text[:500]}")

    def record_status_change(
        self, name: str, old_state: str, new_state: str, matched_text: str
    ) -> None:
        if not self._enabled or not self.is_connected:
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
        if not self.is_connected:
            return "Memory is not connected. Enable memory first."
        assert self._client is not None
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._client.send_message, question)

    # ------------------------------------------------------------------
    # Memory management
    # ------------------------------------------------------------------

    async def clear(self) -> tuple[bool, str]:
        """Clear all memory. Returns (success, message)."""
        if not self.is_connected:
            return False, "Memory is not connected."
        assert self._client is not None
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
        if self._client is None:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, self._client.send_message, text)
        except RuntimeError:
            pass
