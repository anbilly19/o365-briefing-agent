"""Pydantic models for shared data shapes.

The connector's job is to normalise raw source data (O365, Gmail, test JSON)
into TriagedMessage / MessageEnvelope. The rest of the pipeline only
sees these shapes and does not care where the data came from.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field


class TriageCategory(StrEnum):  # must match prompt exactly
    NEEDS_REPLY = "needs_reply"
    NEEDS_ACTION = "needs_action"
    WAITING_ON = "waiting_on"
    FOLLOW_UP = "follow_up"
    FYI = "fyi"


class MessageEnvelope(BaseModel):  # normalised input shape
    id: str
    subject: str
    sender: str
    received_at: datetime
    body_preview: str  # cleaned, truncated body — not the full raw email
    thread_id: str | None = None
    is_reply: bool = False


class TriagedMessage(BaseModel):  # LLM output shape per message
    id: str
    category: TriageCategory
    summary: Annotated[str, Field(max_length=200)]
    due_hint: str | None = None     # e.g. "by Monday", "in 3 days"
    priority_hint: str | None = None  # e.g. "high", "low"
    reply_intent: str | None = None  # only if category == needs_reply


class TriageResult(BaseModel):  # merged output from all batches
    needs_reply: list[TriagedMessage] = []
    needs_action: list[TriagedMessage] = []
    waiting_on: list[TriagedMessage] = []
    follow_up: list[TriagedMessage] = []
    fyi: list[TriagedMessage] = []

    def all_items(self) -> list[TriagedMessage]:
        return (
            self.needs_reply
            + self.needs_action
            + self.waiting_on
            + self.follow_up
            + self.fyi
        )


class CalendarEvent(BaseModel):
    id: str
    subject: str
    start: datetime
    end: datetime
    location: str | None = None
    is_online: bool = False
    attendees: list[str] = []
