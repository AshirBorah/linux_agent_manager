from __future__ import annotations

import asyncio
import errno
import fcntl
import os
import pty
import signal
import struct
import subprocess
import termios
from typing import Callable


class PTYProcess:
    def __init__(self) -> None:
        self._master_fd: int | None = None
        self._slave_fd: int | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._on_data: Callable[[bytes], None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(
        self,
        shell: str = "/bin/bash",
        cwd: str = ".",
        env: dict[str, str] | None = None,
        command: list[str] | None = None,
        rows: int = 24,
        cols: int = 80,
    ) -> None:
        master_fd, slave_fd = pty.openpty()
        self._master_fd = master_fd
        self._slave_fd = slave_fd

        # Set PTY size BEFORE spawning child so it inherits correct dimensions.
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)

        spawn_env = os.environ.copy()
        if env:
            spawn_env.update(env)
        spawn_env.setdefault("TERM", "xterm-256color")

        process_args = command if command else [shell]

        self._process = subprocess.Popen(
            process_args,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd,
            env=spawn_env,
            start_new_session=True,
        )

        # Slave fd is now owned by the child — close our copy.
        os.close(slave_fd)
        self._slave_fd = None

        # Make master non-blocking.
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def attach_to_loop(
        self,
        loop: asyncio.AbstractEventLoop,
        on_data_callback: Callable[[bytes], None],
    ) -> None:
        if self._master_fd is None:
            raise RuntimeError("PTYProcess not started")
        self._loop = loop
        self._on_data = on_data_callback
        loop.add_reader(self._master_fd, self._on_readable)

    def _on_readable(self) -> None:
        assert self._master_fd is not None
        try:
            data = os.read(self._master_fd, 65536)
        except OSError as exc:
            if exc.errno == errno.EIO:
                # EIO means the child closed its side — treat as EOF.
                self._detach_reader()
                if self._on_data:
                    self._on_data(b"")
                return
            # Any other OSError (e.g. EBADF after close) — log and treat as EOF.
            import logging

            logging.getLogger("tame.pty").warning(
                "Unexpected OSError on PTY read (errno=%s): %s", exc.errno, exc
            )
            self._detach_reader()
            if self._on_data:
                self._on_data(b"")
            return
        if not data:
            self._detach_reader()
        if self._on_data:
            self._on_data(data)

    def _detach_reader(self) -> None:
        if self._loop and self._master_fd is not None:
            try:
                self._loop.remove_reader(self._master_fd)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def write(self, data: str) -> None:
        if self._master_fd is None:
            raise RuntimeError("PTYProcess not started")
        os.write(self._master_fd, data.encode())

    def resize(self, rows: int, cols: int) -> None:
        if self._master_fd is None:
            raise RuntimeError("PTYProcess not started")
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)
        if self._process and self.is_alive:
            self.send_signal(signal.SIGWINCH)

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def send_signal(self, sig: int) -> None:
        if self._process is None:
            raise RuntimeError("PTYProcess not started")
        try:
            os.killpg(os.getpgid(self._process.pid), sig)
        except ProcessLookupError:
            pass

    def pause(self) -> None:
        self.send_signal(signal.SIGSTOP)

    def resume(self) -> None:
        self.send_signal(signal.SIGCONT)

    def terminate(self, kill_timeout: float = 3.0) -> None:
        if self._process is None:
            return
        try:
            self.send_signal(signal.SIGTERM)
            try:
                self._process.wait(timeout=kill_timeout)
            except subprocess.TimeoutExpired:
                self.send_signal(signal.SIGKILL)
                self._process.wait(timeout=5.0)
        except Exception:
            pass  # Process already dead — nothing to do.

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_alive(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    @property
    def exit_code(self) -> int | None:
        if self._process is None:
            return None
        return self._process.poll()

    @property
    def pid(self) -> int | None:
        if self._process is None:
            return None
        return self._process.pid

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._detach_reader()
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None
        if self._process is not None:
            if self.is_alive:
                self.terminate()
            self._process = None
        self._on_data = None
        self._loop = None
