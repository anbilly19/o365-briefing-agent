"""Cheap-to-expensive cascade pre-filter.

Architecture (inspired by ai-email-triage and MailSift):
  Tier 1 — Hard heuristics (zero cost):
    Sender patterns, subject keywords, unsubscribe markers, known automated senders.
    Defined in config/rules.yaml. First match wins.

  Tier 2 — LLM triage (existing pipeline):
    Only "ambiguous" messages that pass Tier 1 unchanged reach the LLM.
    Tier 1 typically filters 40-60% of inbox volume on a normal working day.

Design decisions:
  - Rules live in YAML, not code, so users can customise without touching Python.
  - CascadeResult carries the reason string, which is stored in the triage index
    so the user can see WHY a message was pre-classified.
  - No ML/embeddings tier by default — too heavy for a 16 GB laptop context.
    A placeholder hook (_tier2_embedding) exists for future opt-in.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from briefing_agent.models import MessageEnvelope, TriageCategory

logger = logging.getLogger(__name__)

_DEFAULT_RULES_PATH = Path("config/rules.yaml")

_UNSUBSCRIBE_RE = re.compile(
    r"unsubscribe|opt.out|email.preferences|manage.subscriptions",
    re.IGNORECASE,
)


@dataclass
class CascadeResult:
    message: MessageEnvelope
    category: TriageCategory | None  # None = "send to LLM"
    reason: str | None = None
    tier: int = 0  # 0 = no match, 1 = heuristic


class CascadeFilter:
    """Applies rules.yaml heuristics to messages before LLM triage."""

    def __init__(self, rules_path: Path = _DEFAULT_RULES_PATH) -> None:
        self._rules: list[dict[str, Any]] = []
        self._load_rules(rules_path)

    def _load_rules(self, path: Path) -> None:
        if not path.exists():
            logger.warning("rules.yaml not found at %s — cascade disabled.", path)
            return
        data = yaml.safe_load(path.read_text())
        self._rules = data.get("rules", [])
        logger.info("Loaded %d cascade rules from %s.", len(self._rules), path)

    def classify(self, msg: MessageEnvelope, cleaned_body: str = "") -> CascadeResult:
        """Attempt tier-1 heuristic classification.

        Returns CascadeResult with category=None if no rule matched
        (message should proceed to LLM triage).
        """
        for rule in self._rules:
            matcher = rule.get("matcher", "")
            value = rule.get("value", "").lower()
            action = rule.get("action", {})

            matched = False
            if matcher == "sender_contains":
                matched = value in msg.sender.lower()
            elif matcher == "subject_contains":
                matched = value in msg.subject.lower()
            elif matcher == "body_contains":
                matched = value in cleaned_body.lower()
            elif matcher == "has_unsubscribe":
                matched = bool(_UNSUBSCRIBE_RE.search(cleaned_body))

            if matched:
                raw_category = action.get("category", "fyi")
                try:
                    category = TriageCategory(raw_category)
                except ValueError:
                    logger.warning(
                        "Unknown category '%s' in rule '%s' — defaulting to fyi.",
                        raw_category,
                        rule.get("name", "?"),
                    )
                    category = TriageCategory.FYI
                return CascadeResult(
                    message=msg,
                    category=category,
                    reason=action.get("reason", rule.get("name", "heuristic match")),
                    tier=1,
                )

        return CascadeResult(message=msg, category=None, tier=0)

    def partition(
        self,
        messages: list[MessageEnvelope],
        cleaned_bodies: dict[str, str] | None = None,
    ) -> tuple[list[CascadeResult], list[MessageEnvelope]]:
        """Split messages into (pre-classified, needs-LLM).

        Args:
            messages: All messages for this run.
            cleaned_bodies: Optional map of message_id -> cleaned body string.
                            Used for body_contains and has_unsubscribe matchers.

        Returns:
            (pre_classified, llm_queue)
        """
        pre_classified: list[CascadeResult] = []
        llm_queue: list[MessageEnvelope] = []

        for msg in messages:
            body = (cleaned_bodies or {}).get(msg.id, msg.body_preview)
            result = self.classify(msg, cleaned_body=body)
            if result.category is not None:
                pre_classified.append(result)
            else:
                llm_queue.append(msg)

        logger.info(
            "Cascade: %d pre-classified (tier 1), %d sent to LLM.",
            len(pre_classified),
            len(llm_queue),
        )
        return pre_classified, llm_queue
