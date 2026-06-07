"""Tests for tui/review.py.

Focuses on testable pure functions and async logic.
Prompt interaction (Prompt.ask) is excluded from tests — that requires
a live terminal. Integration is covered by manual QA.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from briefing_agent.category_config import CategoryConfig
from briefing_agent.memory import MemoryDB
from briefing_agent.models import RunStatus, TriageCategory, TriagedMessage
from briefing_agent.tui.review import (
    _reason_badge,
    _sender_short,
    _truncate,
    _resolve_run_id,
    _load_run_rows,
    build_category_table,
    run_review,
)


# ---------------------------------------------------------------------------
# Pure helper tests
# ---------------------------------------------------------------------------

def test_sender_short_short_string() -> None:
    assert _sender_short("a@b.com") == "a@b.com"


def test_sender_short_truncates() -> None:
    long = "very.long.address@example-company.co.uk"
    result = _sender_short(long, max_len=20)
    assert len(result) <= 20
    assert result.endswith("…")


def test_sender_short_exact_boundary() -> None:
    s = "a" * 24
    assert _sender_short(s, max_len=24) == s
    assert not _sender_short(s, max_len=24).endswith("…")


def test_truncate_short() -> None:
    assert _truncate("hello") == "hello"


def test_truncate_none() -> None:
    assert _truncate(None) == ""


def test_truncate_long() -> None:
    text = "x" * 100
    result = _truncate(text, max_len=20)
    assert len(result) <= 20
    assert result.endswith("…")


def test_truncate_exact() -> None:
    text = "a" * 60
    assert _truncate(text, max_len=60) == text


def test_reason_badge_llm() -> None:
    assert _reason_badge(None) == "llm"
    assert _reason_badge("llm") == "llm"
    assert _reason_badge("LLM triage") == "llm"


def test_reason_badge_rule() -> None:
    assert _reason_badge("heuristic: noreply sender") == "rule"
    assert _reason_badge("rule match") == "rule"


def test_reason_badge_feedback() -> None:
    assert _reason_badge("feedback override") == "fb"
    assert _reason_badge("override by user") == "fb"


# ---------------------------------------------------------------------------
# build_category_table
# ---------------------------------------------------------------------------

def _make_mock_row(msg_id: str = "msg_1", summary: str = "Test", reason: str = "llm") -> MagicMock:
    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "id": msg_id,
        "category": "needs_reply",
        "reason": reason,
        "summary": summary,
        "classified_at": "2026-06-01T10:00:00+00:00",
    }[key]
    return row


def test_build_category_table_returns_table() -> None:
    from rich.table import Table
    cfg = CategoryConfig(config_path=Path("config/categories.yaml"))
    rows = [_make_mock_row("m1"), _make_mock_row("m2")]
    table = build_category_table(rows, TriageCategory.NEEDS_REPLY, cfg, start_index=1)
    assert isinstance(table, Table)


def test_build_category_table_empty_rows() -> None:
    from rich.table import Table
    cfg = CategoryConfig(config_path=Path("config/categories.yaml"))
    table = build_category_table([], TriageCategory.FYI, cfg)
    assert isinstance(table, Table)


def test_build_category_table_fallback_config() -> None:
    """Should not crash if categories.yaml is missing."""
    from rich.table import Table
    cfg = CategoryConfig(config_path=Path("/nonexistent/categories.yaml"))
    rows = [_make_mock_row()]
    table = build_category_table(rows, TriageCategory.NEEDS_ACTION, cfg)
    assert isinstance(table, Table)


# ---------------------------------------------------------------------------
# _resolve_run_id — async DB tests
# ---------------------------------------------------------------------------

@pytest.fixture
async def db(tmp_path: Path) -> MemoryDB:
    mem = MemoryDB(db_path=tmp_path / "test.db")
    await mem.open()
    yield mem
    await mem.close()


async def test_resolve_run_id_explicit(db: MemoryDB) -> None:
    run_id = await db.start_run()
    await db.finish_run(run_id, [])
    resolved = await _resolve_run_id(db, run_id)
    assert resolved == run_id


async def test_resolve_run_id_latest(db: MemoryDB) -> None:
    run1 = await db.start_run()
    await db.finish_run(run1, [])
    import asyncio; await asyncio.sleep(0.01)  # ensure ordering
    run2 = await db.start_run()
    await db.finish_run(run2, [])
    resolved = await _resolve_run_id(db, None)
    assert resolved == run2


async def test_resolve_run_id_no_completed_runs(db: MemoryDB) -> None:
    await db.start_run()  # in_progress, not complete
    resolved = await _resolve_run_id(db, None)
    assert resolved is None


async def test_resolve_run_id_nonexistent(db: MemoryDB) -> None:
    resolved = await _resolve_run_id(db, "00000000-0000-0000-0000-000000000000")
    assert resolved is None


# ---------------------------------------------------------------------------
# _load_run_rows — grouping logic
# ---------------------------------------------------------------------------

async def test_load_run_rows_groups_by_category(db: MemoryDB) -> None:
    run_id = await db.start_run()
    msgs = [
        TriagedMessage(id="m1", category=TriageCategory.NEEDS_REPLY, summary="Reply 1"),
        TriagedMessage(id="m2", category=TriageCategory.FYI, summary="FYI 1"),
        TriagedMessage(id="m3", category=TriageCategory.NEEDS_REPLY, summary="Reply 2"),
    ]
    await db.finish_run(run_id, msgs)
    grouped = await _load_run_rows(db, run_id)
    assert len(grouped[TriageCategory.NEEDS_REPLY]) == 2
    assert len(grouped[TriageCategory.FYI]) == 1
    assert len(grouped[TriageCategory.NEEDS_ACTION]) == 0


async def test_load_run_rows_empty_run(db: MemoryDB) -> None:
    run_id = await db.start_run()
    await db.finish_run(run_id, [])
    grouped = await _load_run_rows(db, run_id)
    assert all(len(v) == 0 for v in grouped.values())


# ---------------------------------------------------------------------------
# run_review — read-only mode smoke test
# ---------------------------------------------------------------------------

async def test_run_review_read_only_no_feedback(db: MemoryDB, tmp_path: Path) -> None:
    run_id = await db.start_run()
    msgs = [TriagedMessage(id="m1", category=TriageCategory.NEEDS_REPLY, summary="Test")]
    await db.finish_run(run_id, msgs)

    from rich.console import Console
    import io
    console = Console(file=io.StringIO(), force_terminal=True)

    await run_review(
        run_id=run_id,
        read_only=True,
        db_path=db._path,
        console=console,
    )

    # No feedback should be recorded in read-only mode
    feedback = await db.get_feedback_for_message("m1")
    assert feedback == []


async def test_run_review_no_runs(tmp_path: Path) -> None:
    from rich.console import Console
    import io
    console = Console(file=io.StringIO(), force_terminal=True)

    await run_review(
        run_id=None,
        read_only=True,
        db_path=tmp_path / "empty.db",
        console=console,
    )
    # Should exit gracefully with no crash
