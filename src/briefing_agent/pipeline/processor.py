"""Triage processor: groups by thread, manages token budget, drives LLM batches.

Pipeline per run:
  1. Group messages by thread_id (None → treated as solo messages).
  2. Split into token-aware batches (respects num_ctx).
  3. Truncate message bodies to the per-message budget.
  4. Format each batch using prompts.py templates.
  5. Call OllamaAgent.triage_batch() for each batch.
  6. Merge results into a TriageResult.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from briefing_agent.llm.agent import OllamaAgent
from briefing_agent.models import MessageEnvelope, TriagedMessage, TriageResult
from briefing_agent.prompts import (
    build_triage_prompt,
    format_message_for_prompt,
    format_thread_block,
)
from briefing_agent.token_budget import (
    split_into_token_aware_batches,
    truncate_to_budget,
)

logger = logging.getLogger(__name__)


class TriageProcessor:
    def __init__(
        self,
        agent: OllamaAgent,
        max_batch_size: int = 5,
        weekly_context: str | None = None,
    ) -> None:
        self._agent = agent
        self._max_batch_size = max_batch_size
        self._weekly_context = weekly_context

    async def process(
        self,
        messages: list[MessageEnvelope],
    ) -> TriageResult:
        """Run the full triage pipeline and return a merged TriageResult."""
        if not messages:
            return TriageResult()

        # 1. Group by thread for context-aware classification
        ordered = self._group_by_thread(messages)

        # 2. Split into token-aware batches
        batches = split_into_token_aware_batches(
            ordered,
            num_ctx=self._agent.num_ctx,
            max_batch_size=self._max_batch_size,
        )
        logger.info(
            "Processing %d messages in %d batch(es).", len(messages), len(batches)
        )

        # 3. Process each batch
        all_triaged: list[TriagedMessage] = []
        for i, batch in enumerate(batches, 1):
            # Truncate bodies to fit token budget for this batch size
            truncated = truncate_to_budget(
                batch,
                num_ctx=self._agent.num_ctx,
                batch_size=len(batch),
            )
            prompt = self._build_prompt(truncated)
            try:
                triaged = await self._agent.triage_batch(prompt)
                all_triaged.extend(triaged)
                logger.info("Batch %d/%d: classified %d message(s).", i, len(batches), len(triaged))
            except RuntimeError as exc:
                logger.error("Batch %d/%d failed, skipping: %s", i, len(batches), exc)

        return self._to_triage_result(all_triaged)

    def _group_by_thread(
        self,
        messages: list[MessageEnvelope],
    ) -> list[MessageEnvelope]:
        """Reorder messages so thread siblings are adjacent.

        Within a thread, messages stay in received_at order.
        Solo messages (no thread_id) retain their original position.
        """
        threaded: dict[str, list[MessageEnvelope]] = defaultdict(list)
        solo: list[MessageEnvelope] = []
        seen_threads: list[str] = []

        for msg in messages:
            if msg.thread_id:
                if msg.thread_id not in seen_threads:
                    seen_threads.append(msg.thread_id)
                threaded[msg.thread_id].append(msg)
            else:
                solo.append(msg)

        result: list[MessageEnvelope] = []
        for thread_id in seen_threads:
            sorted_msgs = sorted(threaded[thread_id], key=lambda m: m.received_at)
            result.extend(sorted_msgs)
        result.extend(solo)
        return result

    def _build_prompt(self, batch: list[MessageEnvelope]) -> str:
        """Format a batch of messages into the triage prompt.

        Messages sharing a thread_id are wrapped in a thread context block.
        """
        # Group by thread within this batch
        thread_groups: dict[str | None, list[MessageEnvelope]] = defaultdict(list)
        for msg in batch:
            thread_groups[msg.thread_id].append(msg)

        blocks: list[str] = []
        for thread_id, msgs in thread_groups.items():
            formatted = [
                format_message_for_prompt(
                    msg_id=m.id,
                    sender=m.sender,
                    subject=m.subject,
                    body=m.body_preview,
                    attachments=m.attachments or None,
                    is_reply=m.is_reply,
                )
                for m in msgs
            ]
            if thread_id and len(msgs) > 1:
                blocks.append(format_thread_block(thread_id, formatted))
            else:
                blocks.extend(formatted)

        messages_block = "\n\n".join(blocks)
        return build_triage_prompt(
            messages_block=messages_block,
            weekly_context=self._weekly_context,
        )

    @staticmethod
    def _to_triage_result(items: list[TriagedMessage]) -> TriageResult:
        result = TriageResult()
        for item in items:
            bucket = getattr(result, item.category.value)
            bucket.append(item)
        return result
