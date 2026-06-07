"""Communication summary processor.

Responsible for:
  - Preparing message batches for the model
  - Building the triage prompt
  - Sending each batch to the LLM agent
  - Parsing and validating the JSON response
  - Merging all batch results into one TriageResult

The processor does NOT talk to O365 and does NOT write files.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from briefing_agent.models import MessageEnvelope, TriagedMessage, TriageResult, TriageCategory
from briefing_agent.llm.agent import LLMAgent
from briefing_agent.config import settings

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """
You are a communication triage assistant.
Classify EACH message below into EXACTLY ONE category:
  - needs_reply   : a real person is waiting for your response
  - needs_action  : a concrete task you must do (not a newsletter or FYI)
  - waiting_on    : someone else has the next move
  - follow_up     : revisit later, no immediate action
  - fyi           : informational only, no action required

Rules:
  - Newsletters, promotions, and automated notifications are ALWAYS fyi
  - Meeting reminders are fyi (not waiting_on)
  - A direct question from a real person is needs_reply, not follow_up
  - waiting_on means YOU are not the next person to act

Return a JSON array with one object per message:
[
  {{
    "id": "<message id>",
    "category": "<category>",
    "summary": "<one sentence, max 200 chars>",
    "due_hint": "<timing phrase from email or null>",
    "priority_hint": "<high|medium|low or null>",
    "reply_intent": "<what to reply, only if needs_reply, else null>"
  }}
]

Messages:
{messages_block}
"""


class CommunicationSummaryProcessor:
    def __init__(self) -> None:
        self.agent = LLMAgent()

    async def summarize_messages(self, messages: list[MessageEnvelope]) -> TriageResult:
        batches = [
            messages[i : i + settings.batch_size]
            for i in range(0, len(messages), settings.batch_size)
        ]
        logger.info("Processing %d messages in %d batches", len(messages), len(batches))

        all_items: list[TriagedMessage] = []
        for idx, batch in enumerate(batches, 1):
            logger.info("Batch %d/%d (%d messages)...", idx, len(batches), len(batch))
            items = await self._process_batch(batch)
            all_items.extend(items)

        return self._merge(all_items)

    async def _process_batch(self, batch: list[MessageEnvelope]) -> list[TriagedMessage]:
        messages_block = "\n---\n".join(
            f"ID: {m.id}\nFrom: {m.sender}\nSubject: {m.subject}\nBody: {m.body_preview}"
            for m in batch
        )
        prompt = PROMPT_TEMPLATE.format(messages_block=messages_block)

        raw = await self.agent.complete(
            prompt=prompt,
            num_predict=settings.num_predict,
            num_ctx=settings.num_ctx,
        )

        return self._parse_response(raw, batch)

    def _parse_response(
        self, raw: str, batch: list[MessageEnvelope]
    ) -> list[TriagedMessage]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Strip markdown code fences if model wrapped the JSON
            cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            try:
                data = json.loads(cleaned)
            except json.JSONDecodeError as exc:
                logger.error("JSON parse failed for batch: %s", exc)
                logger.debug("Raw response: %s", raw[:500])
                return self._fallback_fyi(batch)

        items: list[TriagedMessage] = []
        id_set = {m.id for m in batch}
        for obj in data:
            try:
                # Validate category is one we know
                cat = obj.get("category", "fyi")
                if cat not in TriageCategory.__members__.values():
                    cat = "fyi"
                items.append(
                    TriagedMessage(
                        id=obj.get("id", ""),
                        category=TriageCategory(cat),
                        summary=obj.get("summary", "")[:200],
                        due_hint=obj.get("due_hint"),
                        priority_hint=obj.get("priority_hint"),
                        reply_intent=obj.get("reply_intent"),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping malformed item %s: %s", obj, exc)

        # Safety net: any message the model didn't return → fyi
        returned_ids = {i.id for i in items}
        for m in batch:
            if m.id not in returned_ids and m.id in id_set:
                logger.warning("Model did not return id=%s, defaulting to fyi", m.id)
                items.append(TriagedMessage(id=m.id, category=TriageCategory.FYI, summary=m.subject))

        return items

    def _fallback_fyi(self, batch: list[MessageEnvelope]) -> list[TriagedMessage]:
        return [
            TriagedMessage(id=m.id, category=TriageCategory.FYI, summary=m.subject)
            for m in batch
        ]

    @staticmethod
    def _merge(items: list[TriagedMessage]) -> TriageResult:
        result = TriageResult()
        for item in items:
            getattr(result, item.category.value).append(item)
        return result
