"""Microsoft Graph calendar client.

Fetches today's events and normalises into CalendarEvent.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

import httpx

from briefing_agent.graph_client.auth import get_token
from briefing_agent.models import CalendarEvent

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


async def fetch_events() -> list[CalendarEvent]:
    token = get_token()
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=24)

    params = {
        "startDateTime": now.isoformat(),
        "endDateTime": end.isoformat(),
        "$select": "id,subject,start,end,location,isOnlineMeeting,attendees",
        "$orderby": "start/dateTime",
        "$top": 20,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{GRAPH_BASE}/me/calendarView",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        resp.raise_for_status()

    raw_events = resp.json().get("value", [])
    logger.info("Fetched %d calendar events from Graph", len(raw_events))
    return [_normalise(e) for e in raw_events]


def _normalise(raw: dict) -> CalendarEvent:  # type: ignore[type-arg]
    return CalendarEvent(
        id=raw["id"],
        subject=raw.get("subject", "(no subject)"),
        start=datetime.fromisoformat(raw["start"]["dateTime"].rstrip("Z") + "+00:00"),
        end=datetime.fromisoformat(raw["end"]["dateTime"].rstrip("Z") + "+00:00"),
        location=raw.get("location", {}).get("displayName") or None,
        is_online=raw.get("isOnlineMeeting", False),
        attendees=[
            a["emailAddress"]["address"]
            for a in raw.get("attendees", [])
            if "emailAddress" in a
        ],
    )
