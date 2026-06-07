"""Feedback CLI commands.

Allows the user to correct triage decisions from the terminal.

Usage:
    # Mark a message as incorrectly categorised
    briefing-agent feedback wrong <message_id> --new-category needs_reply --run-id <id>

    # Snooze a message (revisit later)
    briefing-agent feedback snooze <message_id> --run-id <id>

    # Override a message to a different category
    briefing-agent feedback override <message_id> --to needs_action --run-id <id>

    # Show recent wrong votes (useful for tuning rules.yaml)
    briefing-agent feedback review-wrong

The feedback is stored in the feedback table in memory.db.
Over time, systematic 'wrong' votes can inform updates to rules.yaml.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import click

from briefing_agent.memory import MemoryDB


def _get_db() -> MemoryDB:
    return MemoryDB(db_path=Path("data/memory.db"))


@click.group(name="feedback")
def feedback_group() -> None:
    """Record corrections to triage decisions."""


@feedback_group.command(name="wrong")
@click.argument("message_id")
@click.option("--new-category", required=True, help="The correct category for this message.")
@click.option("--run-id", required=True, help="The run ID the message belongs to.")
@click.option("--note", default=None, help="Optional explanation.")
def mark_wrong(
    message_id: str,
    new_category: str,
    run_id: str,
    note: str | None,
) -> None:
    """Mark a triage decision as wrong and supply the correct category."""

    async def _run() -> None:
        async with _get_db() as db:
            prev = await db.get_previous_classification(message_id)
            if not prev:
                click.echo(
                    f"[!] No classification found for message '{message_id}'. "
                    "Check the message ID and run ID."
                )
                return
            old_cat = prev["category"]
            await db.record_feedback(
                message_id=message_id,
                run_id=run_id,
                old_category=old_cat,
                new_category=new_category,
                vote="wrong",
                note=note,
            )
            click.echo(
                f"✓ Feedback recorded: '{message_id}' "
                f"{old_cat} → {new_category} (wrong)"
            )

    asyncio.run(_run())


@feedback_group.command(name="snooze")
@click.argument("message_id")
@click.option("--run-id", required=True, help="The run ID the message belongs to.")
@click.option("--note", default=None, help="Optional note for when to revisit.")
def snooze(
    message_id: str,
    run_id: str,
    note: str | None,
) -> None:
    """Snooze a message (revisit later; no category change yet)."""

    async def _run() -> None:
        async with _get_db() as db:
            prev = await db.get_previous_classification(message_id)
            old_cat = prev["category"] if prev else "unknown"
            await db.record_feedback(
                message_id=message_id,
                run_id=run_id,
                old_category=old_cat,
                new_category=old_cat,
                vote="snooze",
                note=note,
            )
            click.echo(f"✓ Message '{message_id}' snoozed.")

    asyncio.run(_run())


@feedback_group.command(name="override")
@click.argument("message_id")
@click.option("--to", "new_category", required=True, help="Target category.")
@click.option("--run-id", required=True, help="The run ID the message belongs to.")
@click.option("--note", default=None)
def override(
    message_id: str,
    new_category: str,
    run_id: str,
    note: str | None,
) -> None:
    """Move a message to a different category."""

    async def _run() -> None:
        async with _get_db() as db:
            prev = await db.get_previous_classification(message_id)
            old_cat = prev["category"] if prev else "unknown"
            await db.record_feedback(
                message_id=message_id,
                run_id=run_id,
                old_category=old_cat,
                new_category=new_category,
                vote="correct",
                note=note,
            )
            click.echo(
                f"✓ Overridden: '{message_id}' "
                f"{old_cat} → {new_category}"
            )

    asyncio.run(_run())


@feedback_group.command(name="review-wrong")
@click.option("--limit", default=20, show_default=True, help="Number of entries to show.")
def review_wrong(limit: int) -> None:
    """Show recent wrong votes. Use to identify patterns for rules.yaml."""

    async def _run() -> None:
        async with _get_db() as db:
            rows = await db.get_recent_wrong_votes(limit=limit)
        if not rows:
            click.echo("No wrong votes recorded yet.")
            return
        click.echo(f"\n{'Message ID':<40} {'Old':^15} {'New':^15} {'Note'}")
        click.echo("-" * 90)
        for row in rows:
            note = row["note"] or ""
            click.echo(
                f"{row['message_id']:<40} "
                f"{row['old_category']:^15} "
                f"{row['new_category']:^15} "
                f"{note}"
            )

    asyncio.run(_run())
