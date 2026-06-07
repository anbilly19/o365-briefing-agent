"""Pydantic models for shared data shapes.

All pipeline components share these types. No component should
define its own private message or event shape.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field


class TriageCategory(StrEnum):
    """Must match the category labels in prompts.TRIAGE_CATEGORIES exactly."""
    NEEDS_REPLY = "needs_reply"
    NEEDS_ACTION = "needs_action"
    WAITING_ON = "waiting_on"
    FOLLOW_UP = "follow_up"
    FYI = "fyi"


class RunStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"


class MessageEnvelope(BaseModel):
    """Normalised input shape — connector-agnostic."""
    id: str
    subject: str
    sender: str
    received_at: datetime
    body_preview: str          # cleaned, truncated body
    thread_id: str | None = None
    is_reply: bool = False
    attachments: list[str] = Field(default_factory=list)  # filenames only, no content


class TriagedMessage(BaseModel):
    """LLM output shape per message — must match JSON schema in prompts.py."""
    id: str
    category: TriageCategory
    summary: Annotated[str, Field(max_length=200)]
    due_hint: str | None = None
    priority_hint: str | None = None
    reply_intent: str | None = None  # only populated when category == needs_reply


class TriageResult(BaseModel):
    """Merged output from all batches."""
    needs_reply: list[TriagedMessage] = Field(default_factory=list)
    needs_action: list[TriagedMessage] = Field(default_factory=list)
    waiting_on: list[TriagedMessage] = Field(default_factory=list)
    follow_up: list[TriagedMessage] = Field(default_factory=list)
    fyi: list[TriagedMessage] = Field(default_factory=list)

    def all_items(self) -> list[TriagedMessage]:
        return (
            self.needs_reply
            + self.needs_action
            + self.waiting_on
            + self.follow_up
            + self.fyi
        )

    def total(self) -> int:
        return len(self.all_items())


class CalendarEvent(BaseModel):
    id: str
    subject: str
    start: datetime
    end: datetime
    location: str | None = None
    is_online: bool = False
    attendees: list[str] = Field(default_factory=list)


class TriagedMessageList(BaseModel):
    """Wrapper so Ollama JSON schema enforcement works on the full batch output."""
    items: list[TriagedMessage]
