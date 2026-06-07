"""Microsoft Graph connector — wraps graph_client/ into the AbstractConnector interface."""

from __future__ import annotations

import logging

from briefing_agent.connectors.base import AbstractConnector
from briefing_agent.graph_client.auth import GraphAuth
from briefing_agent.graph_client.mail import GraphMailClient
from briefing_agent.memory import MemoryDB
from briefing_agent.models import MessageEnvelope

logger = logging.getLogger(__name__)

_DELTA_RESOURCE = "mailbox"


class GraphConnector(AbstractConnector):
    """Fetches messages from Microsoft 365 using the Graph delta API."""

    def __init__(self, auth: GraphAuth, memory: MemoryDB) -> None:
        self._client = GraphMailClient(auth)
        self._memory = memory

    @property
    def source_name(self) -> str:
        return "Microsoft Graph"

    async def fetch_new_messages(self) -> list[MessageEnvelope]:
        delta_token = await self._memory.load_delta_token(_DELTA_RESOURCE)
        messages, new_delta_link = await self._client.fetch_messages_delta(
            delta_token=delta_token
        )
        await self._memory.save_delta_token(_DELTA_RESOURCE, new_delta_link)
        logger.info(
            "[%s] Fetched %d new message(s).", self.source_name, len(messages)
        )
        return messages

    async def send_reply(
        self,
        message_id: str,
        body: str,
        reply_all: bool = False,
    ) -> None:
        # TODO: implement via Graph POST /me/messages/{id}/reply
        raise NotImplementedError("Graph reply not yet implemented.")
