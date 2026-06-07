"""Microsoft Graph mail fetcher.

Features:
  - Delta queries: resumes from last delta token to avoid re-processing.
  - 429 rate limiting: respects Retry-After header with exponential backoff.
  - Attachment metadata: fetches filenames without downloading content.
  - Falls back to full fetch if delta token expired (Graph returns 410 Gone).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from briefing_agent.graph_client.auth import GraphAuth
from briefing_agent.models import MessageEnvelope

logger = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_MAIL_SELECT = "id,subject,sender,receivedDateTime,bodyPreview,conversationId,hasAttachments"
_MAX_RETRIES = 5
_BASE_BACKOFF_S = 1.0


class GraphMailClient:
    def __init__(self, auth: GraphAuth) -> None:
        self._auth = auth

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._auth.get_token()}",
            "Content-Type": "application/json",
        }

    async def _get_with_retry(
        self,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """GET with 429 Retry-After handling and exponential back-off."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(_MAX_RETRIES):
                resp = await client.get(url, headers=self._headers(), params=params)

                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", 2 ** attempt))
                    logger.warning(
                        "Graph API rate limited (429). Waiting %.1fs (attempt %d/%d).",
                        retry_after,
                        attempt + 1,
                        _MAX_RETRIES,
                    )
                    await asyncio.sleep(retry_after)
                    continue

                resp.raise_for_status()
                return resp.json()  # type: ignore[no-any-return]

        raise RuntimeError(f"Graph API rate limit exceeded after {_MAX_RETRIES} retries: {url}")

    async def fetch_messages_delta(
        self,
        delta_token: str | None,
        folder: str = "inbox",
    ) -> tuple[list[MessageEnvelope], str]:
        """Fetch new/changed messages since the last delta token.

        Returns:
            (messages, new_delta_link) — persist new_delta_link for the next run.

        If delta_token is None or the token is expired (Graph returns 410),
        performs a full initial sync and returns all messages.
        """
        if delta_token:
            url = delta_token  # delta_token is itself a full URL on subsequent calls
        else:
            url = (
                f"{_GRAPH_BASE}/me/mailFolders/{folder}/messages/delta"
                f"?$select={_MAIL_SELECT}&$top=50"
            )

        messages: list[MessageEnvelope] = []
        next_link: str | None = None
        delta_link: str | None = None

        while url:
            try:
                data = await self._get_with_retry(url)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 410:
                    # Delta token expired — fall back to full fetch
                    logger.warning(
                        "Delta token expired (410 Gone). Falling back to full fetch."
                    )
                    return await self.fetch_messages_delta(None, folder=folder)
                raise

            for raw in data.get("value", []):
                envelope = self._parse_message(raw)
                if raw.get("hasAttachments"):
                    envelope = envelope.model_copy(
                        update={"attachments": await self._fetch_attachment_names(raw["id"])}
                    )
                messages.append(envelope)

            next_link = data.get("@odata.nextLink")
            delta_link = data.get("@odata.deltaLink")
            url = next_link or ""

        if not delta_link:
            raise RuntimeError("Graph delta response did not contain @odata.deltaLink")

        return messages, delta_link

    async def _fetch_attachment_names(self, message_id: str) -> list[str]:
        """Fetch attachment filenames only (no content download)."""
        url = f"{_GRAPH_BASE}/me/messages/{message_id}/attachments"
        params = {"$select": "name"}
        try:
            data = await self._get_with_retry(url, params=params)
            return [a["name"] for a in data.get("value", []) if a.get("name")]
        except Exception:
            logger.warning("Failed to fetch attachments for message %s", message_id)
            return []

    @staticmethod
    def _parse_message(raw: dict[str, Any]) -> MessageEnvelope:
        from datetime import datetime
        sender_obj = raw.get("sender", {})
        sender_email = (
            sender_obj.get("emailAddress", {}).get("address", "")
        )
        received_raw = raw.get("receivedDateTime", "1970-01-01T00:00:00Z")
        received_at = datetime.fromisoformat(received_raw.replace("Z", "+00:00"))
        return MessageEnvelope(
            id=raw["id"],
            subject=raw.get("subject", "(no subject)"),
            sender=sender_email,
            received_at=received_at,
            body_preview=raw.get("bodyPreview", ""),
            thread_id=raw.get("conversationId"),
            is_reply=bool(raw.get("conversationId")),
        )
