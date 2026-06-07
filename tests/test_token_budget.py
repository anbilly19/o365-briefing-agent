"""Tests for token_budget module."""

from datetime import datetime, timezone

import pytest

from briefing_agent.models import MessageEnvelope
from briefing_agent.token_budget import (
    estimate_tokens,
    body_char_cap,
    split_into_token_aware_batches,
    truncate_to_budget,
    CHARS_PER_TOKEN,
    MIN_BODY_CHARS,
)


def make_msg(id: str, body: str = "Hello world") -> MessageEnvelope:
    return MessageEnvelope(
        id=id,
        subject="Test",
        sender="a@b.com",
        received_at=datetime.now(timezone.utc),
        body_preview=body,
    )


# --- estimate_tokens ---

def test_estimate_tokens_basic() -> None:
    assert estimate_tokens("a" * 400) == 100


def test_estimate_tokens_minimum_one() -> None:
    assert estimate_tokens("") == 1


def test_estimate_tokens_proportional() -> None:
    assert estimate_tokens("x" * 800) == estimate_tokens("x" * 400) * 2


# --- body_char_cap ---

def test_body_char_cap_positive() -> None:
    cap = body_char_cap(num_ctx=8192, batch_size=5)
    assert cap > MIN_BODY_CHARS


def test_body_char_cap_decreases_with_more_messages() -> None:
    cap_5 = body_char_cap(num_ctx=8192, batch_size=5)
    cap_10 = body_char_cap(num_ctx=8192, batch_size=10)
    assert cap_5 > cap_10


def test_body_char_cap_never_below_minimum() -> None:
    # even with a tiny context window, cap stays >= MIN_BODY_CHARS
    cap = body_char_cap(num_ctx=512, batch_size=50)
    assert cap >= MIN_BODY_CHARS


# --- split_into_token_aware_batches ---

def test_split_respects_max_batch_size() -> None:
    msgs = [make_msg(str(i)) for i in range(12)]
    batches = split_into_token_aware_batches(msgs, num_ctx=8192, max_batch_size=5)
    for batch in batches:
        assert len(batch) <= 5


def test_split_covers_all_messages() -> None:
    msgs = [make_msg(str(i)) for i in range(7)]
    batches = split_into_token_aware_batches(msgs, num_ctx=8192, max_batch_size=5)
    recovered = [m for batch in batches for m in batch]
    assert len(recovered) == 7


def test_split_single_large_message_gets_own_batch() -> None:
    large_body = "x" * 30_000
    msgs = [make_msg("big", large_body), make_msg("small")]
    batches = split_into_token_aware_batches(msgs, num_ctx=8192, max_batch_size=5)
    # large message forces a batch boundary
    assert batches[0][0].id == "big"


def test_split_empty_input_returns_empty() -> None:
    assert split_into_token_aware_batches([], num_ctx=8192, max_batch_size=5) == []


def test_split_single_message() -> None:
    msgs = [make_msg("only")]
    batches = split_into_token_aware_batches(msgs, num_ctx=8192, max_batch_size=5)
    assert len(batches) == 1
    assert batches[0][0].id == "only"


# --- truncate_to_budget ---

def test_truncate_shortens_long_body() -> None:
    long_body = "z" * 10_000
    msgs = [make_msg("1", long_body)]
    result = truncate_to_budget(msgs, num_ctx=8192, batch_size=5)
    assert len(result[0].body_preview) < len(long_body)


def test_truncate_does_not_shorten_short_body() -> None:
    short_body = "Hello world"
    msgs = [make_msg("1", short_body)]
    result = truncate_to_budget(msgs, num_ctx=8192, batch_size=5)
    assert result[0].body_preview == short_body


def test_truncate_preserves_original_object() -> None:
    long_body = "a" * 10_000
    msg = make_msg("1", long_body)
    result = truncate_to_budget([msg], num_ctx=8192, batch_size=1)
    # original must be unchanged (model_copy was used)
    assert len(msg.body_preview) == 10_000
    assert len(result[0].body_preview) < 10_000
