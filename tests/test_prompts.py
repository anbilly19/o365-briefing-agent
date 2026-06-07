"""Tests for prompts module."""

import pytest

from briefing_agent.prompts import (
    build_triage_prompt,
    format_message_for_prompt,
    format_thread_block,
    TRIAGE_CATEGORIES,
)


def test_triage_categories_complete() -> None:
    expected = {"needs_reply", "needs_action", "waiting_on", "follow_up", "fyi"}
    assert set(TRIAGE_CATEGORIES) == expected


def test_build_prompt_contains_messages_block() -> None:
    prompt = build_triage_prompt(messages_block="[messages here]")
    assert "[messages here]" in prompt


def test_build_prompt_without_context_has_no_context_block() -> None:
    prompt = build_triage_prompt(messages_block="x")
    assert "CONTEXT FROM LAST 7 DAYS" not in prompt


def test_build_prompt_with_context_includes_it() -> None:
    prompt = build_triage_prompt(
        messages_block="x",
        weekly_context="Pending: review PR #42",
    )
    assert "Pending: review PR #42" in prompt
    assert "CONTEXT FROM LAST 7 DAYS" in prompt


def test_format_message_includes_all_fields() -> None:
    formatted = format_message_for_prompt(
        msg_id="msg_001",
        sender="alice@example.com",
        subject="Review please",
        body="Can you take a look?",
        attachments=["spec.pdf"],
        is_reply=True,
    )
    assert "msg_001" in formatted
    assert "alice@example.com" in formatted
    assert "Review please" in formatted
    assert "spec.pdf" in formatted
    assert "reply" in formatted.lower()


def test_format_message_no_attachments() -> None:
    formatted = format_message_for_prompt(
        msg_id="1", sender="a@b.com", subject="hi", body="body"
    )
    assert "Attachment" not in formatted


def test_format_thread_block_contains_thread_id() -> None:
    block = format_thread_block("thread_xyz", ["msg A", "msg B"])
    assert "thread_xyz" in block
    assert "2" in block  # message count
    assert "msg A" in block
    assert "msg B" in block


def test_all_categories_in_triage_prompt() -> None:
    prompt = build_triage_prompt(messages_block="x")
    for cat in TRIAGE_CATEGORIES:
        assert cat in prompt
