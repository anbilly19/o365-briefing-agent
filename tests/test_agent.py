"""Tests for llm/agent.py using pytest-httpx to mock Ollama API calls."""

from __future__ import annotations

import json

import pytest
from pytest_httpx import HTTPXMock

from briefing_agent.llm.agent import OllamaAgent
from briefing_agent.models import TriageCategory


def _ollama_response(items: list[dict]) -> dict:
    """Build a fake Ollama /api/chat response containing a TriagedMessageList."""
    return {
        "message": {
            "role": "assistant",
            "content": json.dumps({"items": items}),
        }
    }


def _item(
    id: str = "m1",
    category: str = "fyi",
    summary: str = "Test summary",
) -> dict:
    return {
        "id": id,
        "category": category,
        "summary": summary,
        "due_hint": None,
        "priority_hint": None,
        "reply_intent": None,
    }


# --- triage_batch ---

async def test_triage_batch_happy_path(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        json=_ollama_response([_item("m1", "fyi"), _item("m2", "needs_reply")])
    )
    agent = OllamaAgent()
    results = await agent.triage_batch("test prompt")
    assert len(results) == 2
    assert results[0].id == "m1"
    assert results[0].category == TriageCategory.FYI
    assert results[1].category == TriageCategory.NEEDS_REPLY


async def test_triage_batch_direct_list_response(httpx_mock: HTTPXMock) -> None:
    """Ollama may return a bare list instead of {items: [...]}."""
    httpx_mock.add_response(
        json={
            "message": {
                "role": "assistant",
                "content": json.dumps([_item("m1", "fyi")]),
            }
        }
    )
    agent = OllamaAgent()
    results = await agent.triage_batch("test prompt")
    assert len(results) == 1


async def test_triage_batch_invalid_item_skipped(httpx_mock: HTTPXMock) -> None:
    """Items with invalid category should be skipped, not crash."""
    bad = {"id": "m1", "category": "not_a_real_category", "summary": "x"}
    httpx_mock.add_response(
        json={"message": {"role": "assistant", "content": json.dumps({"items": [bad]})}}
    )
    agent = OllamaAgent()
    results = await agent.triage_batch("test prompt")
    assert results == []


async def test_triage_batch_retries_on_http_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=500)
    httpx_mock.add_response(status_code=500)
    httpx_mock.add_response(
        json=_ollama_response([_item("m1")])
    )
    agent = OllamaAgent()
    results = await agent.triage_batch("test prompt")
    assert len(results) == 1


async def test_triage_batch_raises_after_max_retries(httpx_mock: HTTPXMock) -> None:
    for _ in range(3):
        httpx_mock.add_response(status_code=500)
    agent = OllamaAgent()
    with pytest.raises(RuntimeError, match="failed after"):
        await agent.triage_batch("test prompt")


async def test_triage_batch_json_repair_fallback(httpx_mock: HTTPXMock) -> None:
    """Malformed JSON should be repaired, not crash."""
    malformed = '{"items": [{"id": "m1", "category": "fyi", "summary": "ok"' + "}"
    httpx_mock.add_response(
        json={"message": {"role": "assistant", "content": malformed}}
    )
    agent = OllamaAgent()
    # should not raise — json_repair should fix the trailing bracket issue
    results = await agent.triage_batch("test prompt")
    assert isinstance(results, list)


async def test_triage_batch_unexpected_shape_returns_empty(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        json={"message": {"role": "assistant", "content": json.dumps({"wrong": "shape"})}}
    )
    agent = OllamaAgent()
    results = await agent.triage_batch("test prompt")
    assert results == []
