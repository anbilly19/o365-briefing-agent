"""Microsoft Graph mail client.

Fetches messages and normalises them into MessageEnvelope — the shared
message shape. The rest of the pipeline does not care that this came
from O365 vs Gmail vs a test JSON file.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

import httpx

from briefing_agent.graph_client.auth import get_token
from briefing_agent.models import MessageEnvelope
from briefing_agent.config import settings

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


async def fetch_messages() -> list[MessageEnvelope]:
    token = get_token()
    since = (datetime.now(timezone.utc) - timedelta(hours=settings.lookback_hours)).isoformat()

    params = {
        "$filter": f"receivedDateTime ge {since}",
        "$orderby": "receivedDateTime desc",
        "$select": "id,subject,sender,receivedDateTime,bodyPreview,conversationId,isReply",
        "$top": 50,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{GRAPH_BASE}/me/messages",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        resp.raise_for_status()

    raw_messages = resp.json().get("value", [])
    logger.info("Fetched %d raw messages from Graph", len(raw_messages))
    return [_normalise(m) for m in raw_messages]


async def reply_to_message(message_id: str, body_html: str) -> None:
    """Reply inline to a message — stays in the same thread."""
    token = get_token()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{GRAPH_BASE}/me/messages/{message_id}/reply",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": {"body": {"contentType": "HTML", "content": body_html}}},
        )
        resp.raise_for_status()
    logger.info("Replied to message %s", message_id)


def _normalise(raw: dict) -> MessageEnvelope:  # type: ignore[type-arg]
    return MessageEnvelope(
        id=raw["id"],
        subject=raw.get("subject", "(no subject)"),
        sender=raw.get("sender", {}).get("emailAddress", {}).get("address", ""),
        received_at=datetime.fromisoformat(
            raw["receivedDateTime"].rstrip("Z") + "+00:00"
        ),
        body_preview=raw.get("bodyPreview", ""),
        thread_id=raw.get("conversationId"),
        is_reply=raw.get("isReply", False),
    )
