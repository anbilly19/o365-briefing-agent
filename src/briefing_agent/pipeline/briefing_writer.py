"""Briefing writer — converts TriageResult into a human-readable markdown briefing.

The point is NOT to summarise the entire inbox.
The point is to reduce inbox noise to what needs attention.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from briefing_agent.models import TriageResult, TriagedMessage, CalendarEvent


SECTION_EMOJI = {
    "needs_reply": "💬",
    "needs_action": "🔴",
    "waiting_on": "⏳",
    "follow_up": "🔁",
    "fyi": "📋",
}

SECTION_LABEL = {
    "needs_reply": "Needs Reply",
    "needs_action": "Needs Action",
    "waiting_on": "Waiting On",
    "follow_up": "Follow Up",
    "fyi": "FYI",
}


class BriefingWriter:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        result: TriageResult,
        events: list[CalendarEvent] | None = None,
    ) -> Path:
        date_str = datetime.now().strftime("%Y-%m-%d")
        path = self.output_dir / f"briefing_{date_str}.md"

        lines: list[str] = [
            f"# Daily Communication Briefing — {date_str}",
            f"_Generated at {datetime.now().strftime('%H:%M')}_",
            "",
        ]

        # Calendar snapshot
        if events:
            lines += ["## 📅 Today's Calendar", ""]
            for e in sorted(events, key=lambda x: x.start):
                time_str = e.start.strftime("%H:%M")
                lines.append(f"- **{time_str}** — {e.subject}")
            lines.append("")

        # Triage sections in priority order
        for category in ["needs_reply", "needs_action", "waiting_on", "follow_up", "fyi"]:
            items: list[TriagedMessage] = getattr(result, category)
            if not items:
                continue
            emoji = SECTION_EMOJI[category]
            label = SECTION_LABEL[category]
            lines += [f"## {emoji} {label} ({len(items)})", ""]
            for item in items:
                bullet = f"- **{item.summary}**"
                if item.due_hint:
                    bullet += f" _(due: {item.due_hint})_"
                if item.priority_hint:
                    bullet += f" `{item.priority_hint}`"
                lines.append(bullet)
                if item.reply_intent:
                    lines.append(f"  → _{item.reply_intent}_")
            lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")
        return path
