"""Unit tests for CommunicationSummaryProcessor JSON parsing."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from briefing_agent.models import MessageEnvelope, TriageCategory
from briefing_agent.pipeline.processor import CommunicationSummaryProcessor


def make_msg(id: str) -> MessageEnvelope:
    return MessageEnvelope(
        id=id,
        subject="Test subject",
        sender="alice@example.com",
        received_at=datetime.now(timezone.utc),
        body_preview="Test body",
    )


VALID_RESPONSE = '''[
  {
    "id": "msg_001",
    "category": "needs_reply",
    "summary": "Alice is asking for a code review",
    "due_hint": "by Friday",
    "priority_hint": "high",
    "reply_intent": "Confirm availability for review"
  }
]'''


@pytest.mark.asyncio
async def test_valid_json_parsed() -> None:
    processor = CommunicationSummaryProcessor()
    batch = [make_msg("msg_001")]
    items = processor._parse_response(VALID_RESPONSE, batch)
    assert len(items) == 1
    assert items[0].category == TriageCategory.NEEDS_REPLY
    assert items[0].due_hint == "by Friday"


@pytest.mark.asyncio
async def test_markdown_fence_stripped() -> None:
    processor = CommunicationSummaryProcessor()
    batch = [make_msg("msg_001")]
    fenced = f"```json\n{VALID_RESPONSE}\n```"
    items = processor._parse_response(fenced, batch)
    assert len(items) == 1


@pytest.mark.asyncio
async def test_missing_id_fallback_to_fyi() -> None:
    processor = CommunicationSummaryProcessor()
    batch = [make_msg("msg_001"), make_msg("msg_002")]
    # Only returns msg_001
    items = processor._parse_response(VALID_RESPONSE, batch)
    ids = {i.id for i in items}
    assert "msg_002" in ids  # fallback applied
    fyi_items = [i for i in items if i.id == "msg_002"]
    assert fyi_items[0].category == TriageCategory.FYI


@pytest.mark.asyncio
async def test_unknown_category_defaults_to_fyi() -> None:
    processor = CommunicationSummaryProcessor()
    batch = [make_msg("msg_001")]
    bad_response = '[{"id": "msg_001", "category": "urgent_banana", "summary": "test"}]'
    items = processor._parse_response(bad_response, batch)
    assert items[0].category == TriageCategory.FYI
