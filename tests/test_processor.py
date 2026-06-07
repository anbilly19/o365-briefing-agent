"""Tests for pipeline/processor.py."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from briefing_agent.models import (
    MessageEnvelope,
    TriagedMessage,
    TriageCategory,
    TriageResult,
)
from briefing_agent.pipeline.processor import TriageProcessor


def _make_msg(
    id: str,
    thread_id: str | None = None,
    received_offset_s: int = 0,
) -> MessageEnvelope:
    return MessageEnvelope(
        id=id,
        subject=f"Subject {id}",
        sender="a@b.com",
        received_at=datetime(
            2026, 6, 1, 9, 0, received_offset_s, tzinfo=timezone.utc
        ),
        body_preview="Some email body text.",
        thread_id=thread_id,
    )


def _make_triaged(id: str, category: TriageCategory = TriageCategory.FYI) -> TriagedMessage:
    return TriagedMessage(id=id, category=category, summary="Summary")


def _make_agent(return_value: list[TriagedMessage]) -> MagicMock:
    agent = MagicMock()
    agent.num_ctx = 8192
    agent.triage_batch = AsyncMock(return_value=return_value)
    return agent


# --- _group_by_thread ---

def test_group_by_thread_keeps_thread_siblings_adjacent() -> None:
    msgs = [
        _make_msg("a", thread_id="t1"),
        _make_msg("b", thread_id=None),
        _make_msg("c", thread_id="t1"),
    ]
    processor = TriageProcessor(agent=_make_agent([]))
    result = processor._group_by_thread(msgs)
    ids = [m.id for m in result]
    # t1 messages should be adjacent; solo message at the end
    t1_positions = [ids.index("a"), ids.index("c")]
    assert abs(t1_positions[0] - t1_positions[1]) == 1
    assert ids[-1] == "b"


def test_group_by_thread_sorts_thread_by_received_at() -> None:
    msgs = [
        _make_msg("later", thread_id="t1", received_offset_s=10),
        _make_msg("earlier", thread_id="t1", received_offset_s=0),
    ]
    processor = TriageProcessor(agent=_make_agent([]))
    result = processor._group_by_thread(msgs)
    assert result[0].id == "earlier"
    assert result[1].id == "later"


def test_group_by_thread_all_solo() -> None:
    msgs = [_make_msg("a"), _make_msg("b")]
    processor = TriageProcessor(agent=_make_agent([]))
    result = processor._group_by_thread(msgs)
    assert [m.id for m in result] == ["a", "b"]


# --- _build_prompt ---

def test_build_prompt_includes_message_ids() -> None:
    msgs = [_make_msg("msg_001"), _make_msg("msg_002")]
    processor = TriageProcessor(agent=_make_agent([]))
    prompt = processor._build_prompt(msgs)
    assert "msg_001" in prompt
    assert "msg_002" in prompt


def test_build_prompt_thread_block_for_multiple_same_thread() -> None:
    msgs = [_make_msg("a", thread_id="t1"), _make_msg("b", thread_id="t1")]
    processor = TriageProcessor(agent=_make_agent([]))
    prompt = processor._build_prompt(msgs)
    assert "THREAD" in prompt
    assert "t1" in prompt


def test_build_prompt_no_thread_block_for_single() -> None:
    msgs = [_make_msg("a", thread_id="t1")]  # single message in thread
    processor = TriageProcessor(agent=_make_agent([]))
    prompt = processor._build_prompt(msgs)
    assert "THREAD" not in prompt


def test_build_prompt_with_weekly_context() -> None:
    msgs = [_make_msg("a")]
    processor = TriageProcessor(agent=_make_agent([]), weekly_context="Waiting on Bob re: budget")
    prompt = processor._build_prompt(msgs)
    assert "Waiting on Bob" in prompt


# --- process ---

async def test_process_empty_returns_empty_result() -> None:
    processor = TriageProcessor(agent=_make_agent([]))
    result = await processor.process([])
    assert isinstance(result, TriageResult)
    assert result.total() == 0


async def test_process_routes_to_correct_buckets() -> None:
    msgs = [_make_msg("m1"), _make_msg("m2")]
    triaged = [
        _make_triaged("m1", TriageCategory.NEEDS_REPLY),
        _make_triaged("m2", TriageCategory.FYI),
    ]
    processor = TriageProcessor(agent=_make_agent(triaged))
    result = await processor.process(msgs)
    assert len(result.needs_reply) == 1
    assert len(result.fyi) == 1
    assert result.needs_reply[0].id == "m1"


async def test_process_skips_failed_batches() -> None:
    """A batch failure should not crash the whole run."""
    msgs = [_make_msg(str(i)) for i in range(6)]
    agent = MagicMock()
    agent.num_ctx = 8192
    # First batch fails, second succeeds
    agent.triage_batch = AsyncMock(
        side_effect=[RuntimeError("Ollama down"), [_make_triaged("3")]]
    )
    processor = TriageProcessor(agent=agent, max_batch_size=5)
    result = await processor.process(msgs)
    assert result.total() == 1


async def test_process_calls_agent_for_each_batch() -> None:
    msgs = [_make_msg(str(i)) for i in range(6)]
    triaged = [_make_triaged(str(i)) for i in range(6)]
    agent = MagicMock()
    agent.num_ctx = 8192
    agent.triage_batch = AsyncMock(side_effect=[
        triaged[:5],
        triaged[5:],
    ])
    processor = TriageProcessor(agent=agent, max_batch_size=5)
    await processor.process(msgs)
    assert agent.triage_batch.call_count == 2
