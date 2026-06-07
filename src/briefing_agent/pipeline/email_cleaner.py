"""Email cleaner and pre-LLM filter.

Cleans raw messages and filters out low-value content
(newsletters, promotions, automated notifications) BEFORE
sending anything to the local model.

Lesson from the video: one newsletter with tracking links +
image labels + legal footers can be thousands of characters.
Cleaning and filtering before the LLM call makes a big
difference in runtime and output quality.
"""

from __future__ import annotations

import re
from briefing_agent.models import MessageEnvelope

# Sender/subject patterns that are almost never worth LLM time
LOW_VALUE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"no.?reply", re.I),
    re.compile(r"noreply", re.I),
    re.compile(r"newsletter", re.I),
    re.compile(r"unsubscribe", re.I),
    re.compile(r"notification@", re.I),
    re.compile(r"alerts?@", re.I),
    re.compile(r"donotreply", re.I),
    re.compile(r"mailer.daemon", re.I),
    re.compile(r"automated", re.I),
    re.compile(r"invoice.generated", re.I),
    re.compile(r"github\.com/notifications", re.I),
]

SUBJECT_LOW_VALUE: list[re.Pattern[str]] = [
    re.compile(r"\[github\]", re.I),
    re.compile(r"build (passed|failed|succeeded)", re.I),
    re.compile(r"your (weekly|monthly|daily) digest", re.I),
    re.compile(r"^fyi:", re.I),
]

MAX_BODY_CHARS = 800  # truncation limit before sending to LLM


class EmailCleaner:
    def clean_and_filter(
        self, messages: list[MessageEnvelope]
    ) -> tuple[list[MessageEnvelope], list[MessageEnvelope]]:
        """Return (kept, skipped) after cleaning and filtering."""
        kept: list[MessageEnvelope] = []
        skipped: list[MessageEnvelope] = []

        for msg in messages:
            if self._is_low_value(msg):
                skipped.append(msg)
            else:
                kept.append(self._clean(msg))

        return kept, skipped

    @staticmethod
    def _is_low_value(msg: MessageEnvelope) -> bool:
        text = f"{msg.sender} {msg.subject}"
        if any(p.search(text) for p in LOW_VALUE_PATTERNS):
            return True
        if any(p.search(msg.subject) for p in SUBJECT_LOW_VALUE):
            return True
        return False

    @staticmethod
    def _clean(msg: MessageEnvelope) -> MessageEnvelope:
        """Strip noise from body_preview and truncate."""
        body = msg.body_preview

        # Remove URLs
        body = re.sub(r"https?://\S+", "", body)
        # Remove email-style footers
        body = re.sub(
            r"(unsubscribe|view in browser|legal footer|privacy policy)[\s\S]*", "", body, flags=re.I
        )
        # Collapse whitespace
        body = re.sub(r"\s{3,}", "  ", body).strip()
        # Truncate
        body = body[:MAX_BODY_CHARS]

        return msg.model_copy(update={"body_preview": body})
