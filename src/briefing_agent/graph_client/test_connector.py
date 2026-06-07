"""Test connector — loads MessageEnvelope objects from local JSON files.

Use this during Phase 1 development instead of live O365 credentials.
Place test messages in data/inbox/*.json, each matching MessageEnvelope shape.

This connector is API-compatible with O365Connector — swap them in main.py
or via an env var (CONNECTOR=test | o365).
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

from briefing_agent.models import MessageEnvelope, CalendarEvent

DATA_DIR = Path("data/inbox")


class TestConnector:
    async def fetch_messages(self) -> list[MessageEnvelope]:
        messages: list[MessageEnvelope] = []
        for path in sorted(DATA_DIR.glob("*.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                messages.extend(MessageEnvelope(**m) for m in raw)
            else:
                messages.append(MessageEnvelope(**raw))
        return messages

    async def fetch_events(self) -> list[CalendarEvent]:
        return []  # extend when needed
