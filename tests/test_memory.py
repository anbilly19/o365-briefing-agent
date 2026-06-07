"""Tests for the memory module (async SQLite)."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from briefing_agent.memory import MemoryDB
from briefing_agent.models import RunStatus, TriagedMessage, TriageCategory


def _make_msg(id: str = "msg_1") -> TriagedMessage:
    return TriagedMessage(
        id=id,
        category=TriageCategory.NEEDS_REPLY,
        summary="Test summary",
    )


@pytest.fixture
async def db(tmp_path: Path) -> MemoryDB:
    memory = MemoryDB(db_path=tmp_path / "test.db")
    await memory.open()
    yield memory
    await memory.close()


# --- run lifecycle ---

async def test_start_run_returns_id(db: MemoryDB) -> None:
    run_id = await db.start_run()
    assert isinstance(run_id, str)
    assert len(run_id) > 0


async def test_run_initially_in_progress(db: MemoryDB) -> None:
    run_id = await db.start_run()
    row = await db.get_run(run_id)
    assert row["status"] == RunStatus.IN_PROGRESS


async def test_finish_run_marks_complete(db: MemoryDB) -> None:
    run_id = await db.start_run()
    await db.finish_run(run_id, [_make_msg()])
    row = await db.get_run(run_id)
    assert row["status"] == RunStatus.COMPLETE


async def test_finish_run_persists_message_count(db: MemoryDB) -> None:
    run_id = await db.start_run()
    msgs = [_make_msg(f"m{i}") for i in range(5)]
    await db.finish_run(run_id, msgs)
    row = await db.get_run(run_id)
    assert row["message_count"] == 5


async def test_finish_run_with_status_failed(db: MemoryDB) -> None:
    run_id = await db.start_run()
    await db.finish_run(run_id, [], status=RunStatus.FAILED)
    row = await db.get_run(run_id)
    assert row["status"] == RunStatus.FAILED


async def test_detect_stale_runs(db: MemoryDB) -> None:
    run_id = await db.start_run()
    stale = await db.detect_stale_runs()
    assert run_id in stale


async def test_detect_stale_runs_empty_after_complete(db: MemoryDB) -> None:
    run_id = await db.start_run()
    await db.finish_run(run_id, [])
    stale = await db.detect_stale_runs()
    assert run_id not in stale


async def test_mark_run_failed(db: MemoryDB) -> None:
    run_id = await db.start_run()
    await db.mark_run_failed(run_id)
    row = await db.get_run(run_id)
    assert row["status"] == RunStatus.FAILED


# --- delta token management ---

async def test_save_and_load_delta_token(db: MemoryDB) -> None:
    await db.save_delta_token("mailbox", "delta_link_abc")
    token = await db.load_delta_token("mailbox")
    assert token == "delta_link_abc"


async def test_delta_token_upsert(db: MemoryDB) -> None:
    await db.save_delta_token("mailbox", "old_token")
    await db.save_delta_token("mailbox", "new_token")
    token = await db.load_delta_token("mailbox")
    assert token == "new_token"


async def test_load_delta_token_missing_returns_none(db: MemoryDB) -> None:
    token = await db.load_delta_token("calendar")
    assert token is None


async def test_context_manager(tmp_path: Path) -> None:
    async with MemoryDB(db_path=tmp_path / "ctx.db") as mem:
        run_id = await mem.start_run()
        assert run_id
