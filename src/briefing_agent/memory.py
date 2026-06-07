"""Persistent memory for run state, classifications, and Graph delta tokens.

Schema
------
  runs
    id              TEXT PRIMARY KEY
    started_at      TEXT NOT NULL
    finished_at     TEXT
    status          TEXT NOT NULL  -- RunStatus enum value
    message_count   INTEGER DEFAULT 0

  classified_messages
    id              TEXT PRIMARY KEY
    run_id          TEXT NOT NULL REFERENCES runs(id)
    category        TEXT NOT NULL
    summary         TEXT NOT NULL
    due_hint        TEXT
    priority_hint   TEXT
    reply_intent    TEXT
    classified_at   TEXT NOT NULL

  delta_tokens
    resource        TEXT PRIMARY KEY   -- e.g. 'mailbox', 'calendar'
    token           TEXT NOT NULL
    recorded_at     TEXT NOT NULL

Transactions
-----------
Every write is wrapped in a transaction. If a run crashes mid-pipeline the
run row stays in status='in_progress'. On next startup the orchestrator
should call detect_stale_runs() and mark them as 'failed'.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from briefing_agent.models import RunStatus, TriagedMessage

_DEFAULT_DB = Path("data/memory.db")


class MemoryDB:
    def __init__(self, db_path: Path = _DEFAULT_DB) -> None:
        self._path = db_path
        self._db: aiosqlite.Connection | None = None

    # --- lifecycle ---

    async def open(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._apply_schema()
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def __aenter__(self) -> "MemoryDB":
        await self.open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    # --- schema ---

    async def _apply_schema(self) -> None:
        assert self._db
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                id            TEXT PRIMARY KEY,
                started_at    TEXT NOT NULL,
                finished_at   TEXT,
                status        TEXT NOT NULL DEFAULT 'in_progress',
                message_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS classified_messages (
                id            TEXT PRIMARY KEY,
                run_id        TEXT NOT NULL REFERENCES runs(id),
                category      TEXT NOT NULL,
                summary       TEXT NOT NULL,
                due_hint      TEXT,
                priority_hint TEXT,
                reply_intent  TEXT,
                classified_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS delta_tokens (
                resource    TEXT PRIMARY KEY,
                token       TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            );
        """)

    # --- run management ---

    async def start_run(self) -> str:
        """Insert a new run row with status=in_progress. Returns the run id."""
        run_id = str(uuid.uuid4())
        now = _now_iso()
        assert self._db
        async with self._db.execute(
            "INSERT INTO runs (id, started_at, status) VALUES (?, ?, ?)",
            (run_id, now, RunStatus.IN_PROGRESS),
        ):
            pass
        await self._db.commit()
        return run_id

    async def finish_run(
        self,
        run_id: str,
        messages: list[TriagedMessage],
        status: RunStatus = RunStatus.COMPLETE,
    ) -> None:
        """Persist all triaged messages and mark the run as complete/failed.

        All writes are wrapped in a single transaction. If anything fails,
        none of the classifications are committed.
        """
        now = _now_iso()
        assert self._db
        async with self._db.execute("BEGIN"):
            pass
        try:
            for msg in messages:
                await self._db.execute(
                    """
                    INSERT OR REPLACE INTO classified_messages
                        (id, run_id, category, summary, due_hint,
                         priority_hint, reply_intent, classified_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        msg.id,
                        run_id,
                        msg.category,
                        msg.summary,
                        msg.due_hint,
                        msg.priority_hint,
                        msg.reply_intent,
                        now,
                    ),
                )
            await self._db.execute(
                """
                UPDATE runs
                SET status=?, finished_at=?, message_count=?
                WHERE id=?
                """,
                (status, now, len(messages), run_id),
            )
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise

    async def detect_stale_runs(self) -> list[str]:
        """Return run ids that are still in_progress (crashed previously)."""
        assert self._db
        async with self._db.execute(
            "SELECT id FROM runs WHERE status = ?", (RunStatus.IN_PROGRESS,)
        ) as cur:
            rows = await cur.fetchall()
        return [row["id"] for row in rows]

    async def mark_run_failed(self, run_id: str) -> None:
        assert self._db
        await self._db.execute(
            "UPDATE runs SET status=?, finished_at=? WHERE id=?",
            (RunStatus.FAILED, _now_iso(), run_id),
        )
        await self._db.commit()

    # --- delta token management ---

    async def save_delta_token(self, resource: str, token: str) -> None:
        assert self._db
        await self._db.execute(
            """
            INSERT INTO delta_tokens (resource, token, recorded_at)
            VALUES (?, ?, ?)
            ON CONFLICT(resource) DO UPDATE SET token=excluded.token,
                                                recorded_at=excluded.recorded_at
            """,
            (resource, token, _now_iso()),
        )
        await self._db.commit()

    async def load_delta_token(self, resource: str) -> str | None:
        assert self._db
        async with self._db.execute(
            "SELECT token FROM delta_tokens WHERE resource = ?", (resource,)
        ) as cur:
            row = await cur.fetchone()
        return row["token"] if row else None

    # --- query helpers ---

    async def get_run(self, run_id: str) -> aiosqlite.Row | None:
        assert self._db
        async with self._db.execute(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        ) as cur:
            return await cur.fetchone()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
