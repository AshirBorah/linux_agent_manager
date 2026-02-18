from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from letta_client import Letta

from .prompts import AGENT_NAME, SYSTEM_PROMPT

log = logging.getLogger("tame.letta")


class LettaClient:
    """Thin wrapper around the Letta SDK for TAME's memory agent."""

    def __init__(self, server_url: str = "http://localhost:8283") -> None:
        self._server_url = server_url
        self._client: Letta | None = None
        self._agent_id: str | None = None

    def connect(self) -> bool:
        """Attempt to connect to the Letta server and ensure the agent exists.

        Returns True on success, False on failure.
        """
        try:
            from letta_client import Letta

            self._client = Letta(base_url=self._server_url)
            self._agent_id = self._get_or_create_agent()
            return True
        except Exception:
            log.exception("Failed to connect to Letta server at %s", self._server_url)
            self._client = None
            self._agent_id = None
            return False

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._agent_id is not None

    def _get_or_create_agent(self) -> str:
        """Find existing tame-memory agent or create a new one."""
        assert self._client is not None
        agents = self._client.agents.list()
        for agent in agents:
            if agent.name == AGENT_NAME:
                log.info("Found existing Letta agent: %s", agent.id)
                return agent.id

        agent = self._client.agents.create(
            name=AGENT_NAME,
            system=SYSTEM_PROMPT,
        )
        log.info("Created Letta agent: %s", agent.id)
        return agent.id

    def send_message(self, text: str) -> str:
        """Send a message to the memory agent and return the response text."""
        if not self.is_connected:
            return ""
        assert self._client is not None and self._agent_id is not None
        try:
            response = self._client.agents.messages.create(
                agent_id=self._agent_id,
                messages=[{"role": "user", "content": text}],
            )
            # Extract text from response messages
            parts: list[str] = []
            for msg in response.messages:
                if hasattr(msg, "content") and msg.content:
                    parts.append(msg.content)
            return "\n".join(parts) if parts else "(no response)"
        except Exception:
            log.exception("Failed to send message to Letta agent")
            return "(error communicating with Letta)"

    def clear_memory(self) -> bool:
        """Delete and recreate the agent to clear all memory."""
        if not self.is_connected:
            return False
        assert self._client is not None and self._agent_id is not None
        try:
            self._client.agents.delete(agent_id=self._agent_id)
            self._agent_id = self._get_or_create_agent()
            log.info("Cleared Letta memory (agent recreated)")
            return True
        except Exception:
            log.exception("Failed to clear Letta memory")
            return False
