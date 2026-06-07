"""IMAP connector (stub — planned for Phase 5).

This file establishes the interface contract.
Implementation will use Python's stdlib `imaplib` or `aioimaplib`
to avoid a heavy dependency.

Design notes:
  - Use IMAP SINCE + UID SEARCH to replicate delta-query semantics.
  - Store last-seen UID in memory.delta_tokens with resource='imap:{host}:{folder}'.
  - Respect IMAP IDLE for near-real-time if needed.
"""

from __future__ import annotations

from briefing_agent.connectors.base import AbstractConnector
from briefing_agent.models import MessageEnvelope


class ImapConnector(AbstractConnector):
    """IMAP connector stub. Not yet implemented."""

    def __init__(self, host: str, port: int, username: str, password: str) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password

    @property
    def source_name(self) -> str:
        return f"IMAP ({self._host})"

    async def fetch_new_messages(self) -> list[MessageEnvelope]:
        raise NotImplementedError(
            "ImapConnector.fetch_new_messages is not yet implemented. "
            "Use GraphConnector for now."
        )

    async def send_reply(
        self,
        message_id: str,
        body: str,
        reply_all: bool = False,
    ) -> None:
        raise NotImplementedError(
            "ImapConnector.send_reply is not yet implemented."
        )
