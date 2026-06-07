"""Token budget management for local LLM batching.

Why this matters:
  A single email with a long HTML thread can be 3,000+ chars after cleaning.
  At ~4 chars/token the context window fills faster than a fixed batch size implies.
  This module ensures we never send a batch that overflows num_ctx.

Approach:
  Character-based approximation: 1 token ≈ 4 characters.
  Zero extra dependencies — tiktoken is more accurate but adds a large download.
  At batch sizes of 5 emails and num_ctx=8192, the approximation is more than
  accurate enough; it's conservative by design.

Budget allocation per call:
  total_chars_budget  = num_ctx * CHARS_PER_TOKEN
  prompt_overhead     = fixed chars for the prompt template + system prompt
  message_budget      = total_chars_budget - prompt_overhead
  per_message_cap     = message_budget // batch_size  (soft cap per message)
"""

from __future__ import annotations

from briefing_agent.models import MessageEnvelope

CHARS_PER_TOKEN: float = 4.0
PROMPT_OVERHEAD_TOKENS: int = 512   # system prompt + template skeleton
MIN_BODY_CHARS: int = 100            # never truncate below this


def estimate_tokens(text: str) -> int:
    """Estimate token count from character length."""
    return max(1, round(len(text) / CHARS_PER_TOKEN))


def body_char_cap(num_ctx: int, batch_size: int) -> int:
    """Return the max body chars per message for a given context window + batch size."""
    total_budget = num_ctx * CHARS_PER_TOKEN
    available = total_budget - (PROMPT_OVERHEAD_TOKENS * CHARS_PER_TOKEN)
    # Each message also has ~80 chars of metadata (id, sender, subject, labels)
    metadata_overhead = 80 * batch_size
    message_budget = available - metadata_overhead
    per_message = message_budget / max(1, batch_size)
    return max(MIN_BODY_CHARS, int(per_message))


def split_into_token_aware_batches(
    messages: list[MessageEnvelope],
    num_ctx: int,
    max_batch_size: int,
) -> list[list[MessageEnvelope]]:
    """Split messages into batches that fit within num_ctx.

    Algorithm:
      - Walk messages in order.
      - Accumulate into current batch while estimated token count stays under budget.
      - Start a new batch when adding the next message would overflow OR
        when max_batch_size is reached.
    """
    token_budget = num_ctx - PROMPT_OVERHEAD_TOKENS
    batches: list[list[MessageEnvelope]] = []
    current_batch: list[MessageEnvelope] = []
    current_tokens = 0

    for msg in messages:
        msg_tokens = estimate_tokens(
            f"{msg.id} {msg.sender} {msg.subject} {msg.body_preview}"
        )
        over_token_limit = (current_tokens + msg_tokens) > token_budget
        over_size_limit = len(current_batch) >= max_batch_size

        if current_batch and (over_token_limit or over_size_limit):
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0

        current_batch.append(msg)
        current_tokens += msg_tokens

    if current_batch:
        batches.append(current_batch)

    return batches


def truncate_to_budget(
    messages: list[MessageEnvelope],
    num_ctx: int,
    batch_size: int,
) -> list[MessageEnvelope]:
    """Truncate body_preview of each message to fit the per-message char cap."""
    cap = body_char_cap(num_ctx, batch_size)
    result = []
    for msg in messages:
        if len(msg.body_preview) > cap:
            msg = msg.model_copy(update={"body_preview": msg.body_preview[:cap]})
        result.append(msg)
    return result
