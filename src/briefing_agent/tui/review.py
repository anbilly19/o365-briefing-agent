"""Interactive triage review TUI.

Provides a Rich-powered terminal interface for reviewing triage decisions
and recording feedback inline. Designed to be fast: most sessions are
< 30 seconds.

Usage:
    # Review the most recent completed run
    briefing-agent review

    # Review a specific run
    briefing-agent review --run-id <uuid>

    # Review without prompting for overrides (read-only)
    briefing-agent review --read-only

Layout
------
For each non-fyi category (in priority order):

  ✉️  Reply needed  (3)
  ┌────┬────────────────┬───────────────┬──────────────────┬─────────┐
  │ #  │ From           │ Subject         │ Summary           │ Reason  │
  ├────┼────────────────┼───────────────┼──────────────────┼─────────┤
  │ 1  │ alice@co.com   │ Q3 report?      │ Alice needs Q3... │ llm     │
  └────┴────────────────┴───────────────┴──────────────────┴─────────┘

After rendering, if not --read-only, prompts:
    [Enter] accept all  [n] step through overrides  [q] quit

Interactive override flow (per message):
    Accept / Wrong (new category) / Snooze / Skip

All feedback is written to memory.db via MemoryDB.record_feedback().
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import aiosqlite
import click
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table
from rich import box
from rich.text import Text

from briefing_agent.category_config import CategoryConfig
from briefing_agent.memory import MemoryDB
from briefing_agent.models import FeedbackVote, RunStatus, TriageCategory

_CONSOLE = Console()

# Category display order (priority-first, fyi last)
_REVIEW_ORDER = [
    TriageCategory.NEEDS_REPLY,
    TriageCategory.NEEDS_ACTION,
    TriageCategory.WAITING_ON,
    TriageCategory.FOLLOW_UP,
    TriageCategory.FYI,
]

# Rich colour per category
_CATEGORY_COLOUR = {
    TriageCategory.NEEDS_REPLY:  "bold red",
    TriageCategory.NEEDS_ACTION: "bold yellow",
    TriageCategory.WAITING_ON:   "cyan",
    TriageCategory.FOLLOW_UP:    "blue",
    TriageCategory.FYI:          "dim",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sender_short(sender: str, max_len: int = 24) -> str:
    """Return a display-friendly sender string, truncated if needed."""
    if len(sender) <= max_len:
        return sender
    return sender[:max_len - 1] + "…"


def _truncate(text: str | None, max_len: int = 60) -> str:
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"


def _reason_badge(reason: str | None) -> str:
    """Return a short tag: 'llm', 'rule', or 'fb' (feedback override)."""
    if not reason:
        return "llm"
    r = reason.lower()
    if r.startswith("heuristic") or r.startswith("rule"):
        return "rule"
    if r.startswith("feedback") or r.startswith("override"):
        return "fb"
    return "llm"


def build_category_table(
    rows: list[aiosqlite.Row],
    category: TriageCategory,
    cat_config: CategoryConfig,
    start_index: int = 1,
) -> Table:
    """Build a Rich Table for one category group."""
    colour = _CATEGORY_COLOUR.get(category, "white")
    icon = cat_config.icon(category.value)
    label = cat_config.display_name(category.value)
    count = len(rows)

    table = Table(
        title=Text(f"{icon}  {label}  ({count})", style=colour),
        box=box.SIMPLE_HEAD,
        show_footer=False,
        title_justify="left",
        padding=(0, 1),
    )
    table.add_column("#", style="dim", width=3, no_wrap=True)
    table.add_column("From", max_width=26, no_wrap=True)
    table.add_column("Subject", max_width=36, no_wrap=True)
    table.add_column("Summary", max_width=52)
    table.add_column("Via", width=5, justify="center", style="dim")

    for i, row in enumerate(rows, start=start_index):
        table.add_row(
            str(i),
            _sender_short(row["id"]),  # id is message_id; subject not stored — use summary
            _truncate(row["summary"], 34),
            _truncate(row["summary"], 50),
            _reason_badge(row["reason"]),
        )

    return table


def _valid_categories() -> list[str]:
    return [c.value for c in TriageCategory]


# ---------------------------------------------------------------------------
# Interactive override flow
# ---------------------------------------------------------------------------

async def _prompt_overrides(
    rows_by_category: dict[TriageCategory, list[aiosqlite.Row]],
    run_id: str,
    db: MemoryDB,
    console: Console = _CONSOLE,
) -> int:
    """Step through each message and prompt for accept/override/snooze.

    Returns the number of feedback entries recorded.
    """
    recorded = 0
    valid = ", ".join(_valid_categories())

    for category in _REVIEW_ORDER:
        rows = rows_by_category.get(category, [])
        if not rows:
            continue
        for row in rows:
            msg_id = row["id"]
            current_cat = row["category"]
            summary = _truncate(row["summary"], 70)

            console.print(f"\n[bold]{msg_id}[/bold]")
            console.print(f"  Category : [cyan]{current_cat}[/cyan]")
            console.print(f"  Summary  : {summary}")
            console.print(f"  Via      : {_reason_badge(row['reason'])}")

            action = Prompt.ask(
                "  Action",
                choices=["a", "w", "s", "k"],
                default="a",
                show_choices=True,
                console=console,
            )
            # a=accept, w=wrong, s=snooze, k=skip

            if action == "a":
                await db.record_feedback(
                    message_id=msg_id,
                    run_id=run_id,
                    old_category=current_cat,
                    new_category=current_cat,
                    vote=FeedbackVote.CORRECT,
                )
                recorded += 1

            elif action == "w":
                new_cat = Prompt.ask(
                    f"  New category [{valid}]",
                    console=console,
                )
                if new_cat not in _valid_categories():
                    console.print(f"  [red]Unknown category '{new_cat}' — skipping.[/red]")
                    continue
                note = Prompt.ask("  Note (optional)", default="", console=console) or None
                await db.record_feedback(
                    message_id=msg_id,
                    run_id=run_id,
                    old_category=current_cat,
                    new_category=new_cat,
                    vote=FeedbackVote.WRONG,
                    note=note,
                )
                console.print(f"  [green]✓[/green] Marked wrong: {current_cat} → {new_cat}")
                recorded += 1

            elif action == "s":
                note = Prompt.ask("  Snooze note (optional)", default="", console=console) or None
                await db.record_feedback(
                    message_id=msg_id,
                    run_id=run_id,
                    old_category=current_cat,
                    new_category=current_cat,
                    vote=FeedbackVote.SNOOZE,
                    note=note,
                )
                console.print("  [blue]⏳[/blue] Snoozed.")
                recorded += 1

            # action == "k": skip silently

    return recorded


# ---------------------------------------------------------------------------
# Core review logic
# ---------------------------------------------------------------------------

async def _load_run_rows(
    db: MemoryDB,
    run_id: str,
) -> dict[TriageCategory, list[aiosqlite.Row]]:
    """Load all classified messages for a run, grouped by category."""
    assert db._db
    async with db._db.execute(
        """
        SELECT cm.id, cm.category, cm.reason, cm.summary, cm.classified_at
        FROM classified_messages cm
        WHERE cm.run_id = ?
        ORDER BY cm.classified_at ASC
        """,
        (run_id,),
    ) as cur:
        all_rows = await cur.fetchall()

    grouped: dict[TriageCategory, list[aiosqlite.Row]] = {c: [] for c in TriageCategory}
    for row in all_rows:
        try:
            cat = TriageCategory(row["category"])
        except ValueError:
            cat = TriageCategory.FYI
        grouped[cat].append(row)
    return grouped


async def _resolve_run_id(db: MemoryDB, run_id: str | None) -> str | None:
    """Return run_id to review. If None, use the most recent completed run."""
    assert db._db
    if run_id:
        row = await db.get_run(run_id)
        if not row:
            return None
        return run_id

    async with db._db.execute(
        """
        SELECT id FROM runs
        WHERE status = ?
        ORDER BY finished_at DESC
        LIMIT 1
        """,
        (RunStatus.COMPLETE,),
    ) as cur:
        row = await cur.fetchone()
    return row["id"] if row else None


async def run_review(
    run_id: str | None = None,
    read_only: bool = False,
    db_path: Path = Path("data/memory.db"),
    console: Console = _CONSOLE,
) -> None:
    """Main entry point for the review TUI."""
    cat_config = CategoryConfig()

    async with MemoryDB(db_path=db_path) as db:
        resolved_run_id = await _resolve_run_id(db, run_id)
        if not resolved_run_id:
            console.print(
                "[red]No completed runs found.[/red] Run [bold]briefing-agent run[/bold] first."
            )
            return

        run_row = await db.get_run(resolved_run_id)
        total_msgs = run_row["message_count"] if run_row else "?"
        finished_at = run_row["finished_at"] if run_row else "?"

        console.rule(f"[bold]Briefing Review[/bold]  run={resolved_run_id[:8]}…  msgs={total_msgs}  finished={finished_at}")

        rows_by_cat = await _load_run_rows(db, resolved_run_id)

        # Render one table per category (skip empty)
        global_index = 1
        for category in _REVIEW_ORDER:
            rows = rows_by_cat.get(category, [])
            if not rows:
                continue
            table = build_category_table(rows, category, cat_config, start_index=global_index)
            console.print(table)
            global_index += len(rows)

        total_shown = sum(len(v) for v in rows_by_cat.values())
        if total_shown == 0:
            console.print("[dim]No messages to review for this run.[/dim]")
            return

        if read_only:
            console.print("[dim](read-only mode — no feedback recorded)[/dim]")
            return

        # Offer bulk accept or step-through
        console.print()
        top_action = Prompt.ask(
            "[bold]Action[/bold]",
            choices=["a", "n", "q"],
            default="a",
            console=console,
            show_choices=False,
            show_default=False,
            prompt_suffix=" [[green]a[/green]ccept all / [yellow]n[/yellow]ow review / [red]q[/red]uit]: ",
        )

        if top_action == "q":
            return

        if top_action == "a":
            # Record 'correct' for every message in one shot
            count = 0
            for category in _REVIEW_ORDER:
                for row in rows_by_cat.get(category, []):
                    await db.record_feedback(
                        message_id=row["id"],
                        run_id=resolved_run_id,
                        old_category=row["category"],
                        new_category=row["category"],
                        vote=FeedbackVote.CORRECT,
                    )
                    count += 1
            console.print(f"[green]✓[/green] Accepted {count} message(s).")
            return

        # n = step-through override flow
        recorded = await _prompt_overrides(
            rows_by_cat,
            resolved_run_id,
            db,
            console=console,
        )
        console.print(f"\n[green]✓[/green] {recorded} feedback record(s) saved.")


# ---------------------------------------------------------------------------
# Click command (wired into main CLI in main.py)
# ---------------------------------------------------------------------------

@click.command(name="review")
@click.option("--run-id", default=None, help="Run ID to review. Defaults to most recent.")
@click.option("--read-only", is_flag=True, default=False, help="Display only, no feedback recorded.")
def review_command(run_id: str | None, read_only: bool) -> None:
    """Interactively review and correct triage decisions."""
    asyncio.run(run_review(run_id=run_id, read_only=read_only))
