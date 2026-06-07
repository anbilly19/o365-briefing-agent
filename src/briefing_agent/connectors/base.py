"""Abstract base connector interface.

All mail source connectors implement AbstractConnector.
The pipeline only ever calls `fetch_new_messages` and `send_reply`.

Connectors:
  GraphConnector  — Microsoft Graph API (Graph client already in graph_client/)
  ImapConnector   — any IMAP server (generic, planned)
  GmailConnector  — Gmail API (planned)
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from briefing_agent.models import MessageEnvelope


class AbstractConnector(ABC):
    """Interface every mail source connector must implement."""

    @abstractmethod
    async def fetch_new_messages(self) -> list[MessageEnvelope]:
        """Fetch messages that have arrived since the last run.

        Implementations should use delta queries, IMAP SINCE/UID, or equivalent
        to avoid returning already-processed messages.

        Returns an empty list if there is nothing new.
        """
        ...

    @abstractmethod
    async def send_reply(
        self,
        message_id: str,
        body: str,
        reply_all: bool = False,
    ) -> None:
        """Send a reply to a specific message.

        Args:
            message_id: The connector-native message identifier.
            body:       Plain-text reply body.
            reply_all:  If True, reply to all recipients.
        """
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable connector name, e.g. 'Microsoft Graph', 'IMAP'."""
        ...
