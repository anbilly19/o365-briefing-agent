"""Action exporter — writes structured handoff JSON files from TriageResult.

Handoff files are consumed by future pipeline modules
(calendar module, reply drafter, follow-up tracker).

The model classifies. Python formats and routes the result.

Output files:
  - reply_drafts.json    : needs_reply items (intent only, no draft yet)
  - todo_items.json      : needs_action + follow_up items
  - waiting_on.json      : waiting_on items

Note: reply drafting is intentionally deferred. Good reply drafts need
more context (tasks, calendar, meeting notes, previous thread messages).
This file prepares the intent; the draft connector comes later.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from briefing_agent.models import TriageResult, TriagedMessage


class ActionExporter:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(self, result: TriageResult) -> list[Path]:
        date_str = datetime.now().strftime("%Y-%m-%d")
        written: list[Path] = []

        # reply_drafts.json
        if result.needs_reply:
            p = self.output_dir / f"reply_drafts_{date_str}.json"
            self._write_json(p, [
                {
                    "id": item.id,
                    "summary": item.summary,
                    "reply_intent": item.reply_intent,
                    "due_hint": item.due_hint,
                }
                for item in result.needs_reply
            ])
            written.append(p)

        # todo_items.json — needs_action (type=action) + follow_up (type=follow_up)
        todo_items = [
            {
                "id": item.id,
                "type": "action",
                "summary": item.summary,
                "due_hint": item.due_hint,
                "priority_hint": item.priority_hint,
            }
            for item in result.needs_action
        ] + [
            {
                "id": item.id,
                "type": "follow_up",
                "summary": item.summary,
                "due_hint": item.due_hint,
                "priority_hint": item.priority_hint,
            }
            for item in result.follow_up
        ]
        if todo_items:
            p = self.output_dir / f"todo_items_{date_str}.json"
            self._write_json(p, todo_items)
            written.append(p)

        # waiting_on.json
        if result.waiting_on:
            p = self.output_dir / f"waiting_on_{date_str}.json"
            self._write_json(p, [
                {
                    "id": item.id,
                    "summary": item.summary,
                    "due_hint": item.due_hint,
                }
                for item in result.waiting_on
            ])
            written.append(p)

        return written

    @staticmethod
    def _write_json(path: Path, data: list[dict]) -> None:  # type: ignore[type-arg]
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
