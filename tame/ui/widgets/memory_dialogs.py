from __future__ import annotations

from textual import events, work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


class MemoryEnableDialog(ModalScreen[bool]):
    """First-time onboarding dialog for enabling session memory."""

    DEFAULT_CSS = """
    MemoryEnableDialog {
        align: center middle;
    }

    MemoryEnableDialog #mem-enable-box {
        width: 50;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    MemoryEnableDialog .mem-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    MemoryEnableDialog .mem-desc {
        margin-bottom: 1;
    }

    MemoryEnableDialog .mem-server {
        color: $text-muted;
        margin-bottom: 1;
    }

    MemoryEnableDialog #mem-enable-buttons {
        margin-top: 1;
        height: auto;
        align: center middle;
    }

    MemoryEnableDialog .mem-btn {
        margin: 0 1;
    }
    """

    def __init__(self, server_url: str) -> None:
        super().__init__()
        self._server_url = server_url

    def compose(self) -> ComposeResult:
        with Vertical(id="mem-enable-box"):
            yield Label("[bold]Enable Session Memory?[/bold]", classes="mem-title")
            yield Label(
                "TAME can remember what happens across your sessions "
                "— errors, fixes, patterns.",
                classes="mem-desc",
            )
            yield Label(
                "This uses Letta to store session events locally on your machine.",
                classes="mem-desc",
            )
            yield Label(
                f"Server: {self._server_url}\n"
                "(configure in ~/.config/tame/config.toml)",
                classes="mem-server",
            )
            from textual.containers import Horizontal

            with Horizontal(id="mem-enable-buttons"):
                yield Button(
                    "Enable", id="mem-enable-yes", variant="success", classes="mem-btn"
                )
                yield Button(
                    "Cancel", id="mem-enable-no", variant="primary", classes="mem-btn"
                )

    def on_mount(self) -> None:
        self.query_one("#mem-enable-yes", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(event.button.id == "mem-enable-yes")

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            return  # let button handle it
        if event.key == "escape":
            event.stop()
            self.dismiss(False)


class MemoryRecallDialog(ModalScreen[None]):
    """Dialog for querying session memory."""

    DEFAULT_CSS = """
    MemoryRecallDialog {
        align: center middle;
    }

    MemoryRecallDialog #mem-recall-box {
        width: 70;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    MemoryRecallDialog .mem-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    MemoryRecallDialog #mem-recall-input {
        margin-bottom: 1;
    }

    MemoryRecallDialog #mem-recall-response {
        height: auto;
        max-height: 20;
        padding: 1;
        background: $background;
        overflow-y: auto;
    }

    MemoryRecallDialog #mem-recall-footer {
        margin-top: 1;
        height: auto;
        align: center middle;
    }

    MemoryRecallDialog .mem-btn {
        margin: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()

    def compose(self) -> ComposeResult:
        with Vertical(id="mem-recall-box"):
            yield Label("[bold]Ask Memory[/bold]", classes="mem-title")
            yield Input(
                placeholder="What fixed the timeout error?", id="mem-recall-input"
            )
            yield Static("", id="mem-recall-response")
            from textual.containers import Horizontal

            with Horizontal(id="mem-recall-footer"):
                yield Button(
                    "Close", id="mem-recall-close", variant="primary", classes="mem-btn"
                )

    def on_mount(self) -> None:
        self.query_one("#mem-recall-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        question = event.value.strip()
        if not question:
            return
        response_widget = self.query_one("#mem-recall-response", Static)
        response_widget.update("[dim]Thinking...[/dim]")
        self._do_query(question)

    @work(thread=True)
    def _do_query(self, question: str) -> None:
        """Run the Letta query in a background thread."""
        try:
            from tame.integrations.letta import MemoryBridge

            bridge: MemoryBridge | None = getattr(self.app, "_memory_bridge", None)
            if bridge is None:
                self._show_response("Memory is not available.")
                return
            import asyncio

            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(bridge.query(question))
            finally:
                loop.close()
            self._show_response(result)
        except Exception as e:
            self._show_response(f"Error: {e}")

    def _show_response(self, text: str) -> None:
        self.app.call_from_thread(self._update_response, text)

    def _update_response(self, text: str) -> None:
        response_widget = self.query_one("#mem-recall-response", Static)
        response_widget.update(text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(None)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            self.dismiss(None)


class MemoryClearDialog(ModalScreen[bool]):
    """Confirmation dialog for clearing all session memory."""

    DEFAULT_CSS = """
    MemoryClearDialog {
        align: center middle;
    }

    MemoryClearDialog #mem-clear-box {
        width: 50;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    MemoryClearDialog .mem-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    MemoryClearDialog .mem-warn {
        margin-bottom: 1;
    }

    MemoryClearDialog #mem-clear-buttons {
        margin-top: 1;
        height: auto;
        align: center middle;
    }

    MemoryClearDialog .mem-btn {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="mem-clear-box"):
            yield Label("[bold]Clear Session Memory?[/bold]", classes="mem-title")
            yield Label(
                "Clear all session memory? This cannot be undone.",
                classes="mem-warn",
            )
            from textual.containers import Horizontal

            with Horizontal(id="mem-clear-buttons"):
                yield Button(
                    "Clear", id="mem-clear-yes", variant="error", classes="mem-btn"
                )
                yield Button(
                    "Cancel", id="mem-clear-no", variant="primary", classes="mem-btn"
                )

    def on_mount(self) -> None:
        self.query_one("#mem-clear-no", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(event.button.id == "mem-clear-yes")

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            self.dismiss(False)
