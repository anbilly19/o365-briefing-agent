"""O365 connector — single entry point that the pipeline uses.

The connector's job is to pull data from O365 and normalise it
into the shared message/event shapes. The pipeline should not care
where messages came from.
"""

from __future__ import annotations

from briefing_agent.graph_client.mail import fetch_messages
from briefing_agent.graph_client.calendar import fetch_events
from briefing_agent.models import MessageEnvelope, CalendarEvent


class O365Connector:
    async def fetch_messages(self) -> list[MessageEnvelope]:
        return await fetch_messages()

    async def fetch_events(self) -> list[CalendarEvent]:
        return await fetch_events()
