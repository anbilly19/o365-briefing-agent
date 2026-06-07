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
    assert isinstance(run_id, str) and len(run_id) > 0


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


# --- triage index / dedup ---

async def test_was_triaged_returns_false_for_unknown(db: MemoryDB) -> None:
    result = await db.was_triaged("unknown_id")
    assert result is False


async def test_was_triaged_returns_true_after_complete_run(db: MemoryDB) -> None:
    run_id = await db.start_run()
    await db.finish_run(run_id, [_make_msg("msg_abc")])
    assert await db.was_triaged("msg_abc") is True


async def test_was_triaged_false_for_in_progress_run(db: MemoryDB) -> None:
    """A message in an in-progress run should not count as triaged."""
    run_id = await db.start_run()
    await db.finish_run(run_id, [_make_msg("msg_x")], status=RunStatus.IN_PROGRESS)
    # run is still in_progress — was_triaged should return False
    assert await db.was_triaged("msg_x") is False


async def test_get_previous_classification(db: MemoryDB) -> None:
    run_id = await db.start_run()
    msg = _make_msg("msg_q")
    await db.finish_run(run_id, [msg], reasons={"msg_q": "heuristic: noreply"})
    row = await db.get_previous_classification("msg_q")
    assert row is not None
    assert row["reason"] == "heuristic: noreply"
    assert row["category"] == TriageCategory.NEEDS_REPLY


# --- feedback ---

async def test_record_and_retrieve_feedback(db: MemoryDB) -> None:
    run_id = await db.start_run()
    await db.record_feedback(
        message_id="msg_1",
        run_id=run_id,
        old_category="fyi",
        new_category="needs_reply",
        vote="wrong",
        note="This was from my manager",
    )
    rows = await db.get_feedback_for_message("msg_1")
    assert len(rows) == 1
    assert rows[0]["vote"] == "wrong"
    assert rows[0]["note"] == "This was from my manager"


async def test_get_recent_wrong_votes(db: MemoryDB) -> None:
    run_id = await db.start_run()
    await db.record_feedback("m1", run_id, "fyi", "needs_reply", "wrong")
    await db.record_feedback("m2", run_id, "fyi", "needs_action", "correct")
    wrong = await db.get_recent_wrong_votes()
    ids = [r["message_id"] for r in wrong]
    assert "m1" in ids
    assert "m2" not in ids


async def test_feedback_multiple_votes_per_message(db: MemoryDB) -> None:
    run_id = await db.start_run()
    for i in range(3):
        await db.record_feedback("msg_z", run_id, "fyi", "needs_reply", "wrong")
    rows = await db.get_feedback_for_message("msg_z")
    assert len(rows) == 3
