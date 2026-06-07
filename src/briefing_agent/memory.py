"""Persistent memory for run state, classifications, triage index, and feedback.

Schema
------
  runs
    id              TEXT PRIMARY KEY
    started_at      TEXT NOT NULL
    finished_at     TEXT
    status          TEXT NOT NULL  -- RunStatus enum value
    message_count   INTEGER DEFAULT 0

  classified_messages                        <-- per-message triage index
    id              TEXT NOT NULL           -- Graph message id (or RFC Message-ID)
    run_id          TEXT NOT NULL REFERENCES runs(id)
    category        TEXT NOT NULL
    reason          TEXT                    -- 'heuristic: noreply sender' or 'llm'
    summary         TEXT NOT NULL
    due_hint        TEXT
    priority_hint   TEXT
    reply_intent    TEXT
    classified_at   TEXT NOT NULL
    PRIMARY KEY (id, run_id)               -- same msg can appear in multiple runs

  delta_tokens
    resource        TEXT PRIMARY KEY
    token           TEXT NOT NULL
    recorded_at     TEXT NOT NULL

  feedback
    id              INTEGER PRIMARY KEY AUTOINCREMENT
    message_id      TEXT NOT NULL
    run_id          TEXT NOT NULL
    old_category    TEXT NOT NULL
    new_category    TEXT NOT NULL
    vote            TEXT NOT NULL  -- 'correct' | 'wrong' | 'snooze'
    note            TEXT
    recorded_at     TEXT NOT NULL

Transactions
-----------
Every multi-step write is wrapped in an explicit transaction.
If a run crashes mid-pipeline the run row stays in status='in_progress'.
Call detect_stale_runs() on next startup and mark them as 'failed'.

Triage index / dedup
--------------------
was_triaged(message_id) checks whether a message was classified in any
complete run. This lets the pipeline skip re-triaging unchanged messages
across runs when combined with delta queries.
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
                id            TEXT NOT NULL,
                run_id        TEXT NOT NULL REFERENCES runs(id),
                category      TEXT NOT NULL,
                reason        TEXT,
                summary       TEXT NOT NULL,
                due_hint      TEXT,
                priority_hint TEXT,
                reply_intent  TEXT,
                classified_at TEXT NOT NULL,
                PRIMARY KEY (id, run_id)
            );

            CREATE INDEX IF NOT EXISTS idx_cm_message_id
                ON classified_messages(id);

            CREATE TABLE IF NOT EXISTS delta_tokens (
                resource    TEXT PRIMARY KEY,
                token       TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id    TEXT NOT NULL,
                run_id        TEXT NOT NULL,
                old_category  TEXT NOT NULL,
                new_category  TEXT NOT NULL,
                vote          TEXT NOT NULL,
                note          TEXT,
                recorded_at   TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_feedback_message_id
                ON feedback(message_id);
        """)

    # --- run management ---

    async def start_run(self) -> str:
        run_id = str(uuid.uuid4())
        now = _now_iso()
        assert self._db
        await self._db.execute(
            "INSERT INTO runs (id, started_at, status) VALUES (?, ?, ?)",
            (run_id, now, RunStatus.IN_PROGRESS),
        )
        await self._db.commit()
        return run_id

    async def finish_run(
        self,
        run_id: str,
        messages: list[TriagedMessage],
        status: RunStatus = RunStatus.COMPLETE,
        reasons: dict[str, str] | None = None,
    ) -> None:
        """Persist all triaged messages and mark the run as complete/failed.

        Args:
            run_id:   The run being finalised.
            messages: All TriagedMessage objects from this run.
            status:   Final run status.
            reasons:  Optional map of message_id -> reason string
                      (e.g. 'heuristic: noreply sender' or 'llm').
                      Used to populate the triage index.
        """
        now = _now_iso()
        reasons = reasons or {}
        assert self._db
        await self._db.execute("BEGIN")
        try:
            for msg in messages:
                await self._db.execute(
                    """
                    INSERT OR REPLACE INTO classified_messages
                        (id, run_id, category, reason, summary, due_hint,
                         priority_hint, reply_intent, classified_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        msg.id,
                        run_id,
                        msg.category,
                        reasons.get(msg.id, "llm"),
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

    # --- triage index / dedup ---

    async def was_triaged(self, message_id: str) -> bool:
        """Return True if this message was classified in any completed run."""
        assert self._db
        async with self._db.execute(
            """
            SELECT 1 FROM classified_messages cm
            JOIN runs r ON cm.run_id = r.id
            WHERE cm.id = ? AND r.status = ?
            LIMIT 1
            """,
            (message_id, RunStatus.COMPLETE),
        ) as cur:
            return await cur.fetchone() is not None

    async def get_previous_classification(
        self, message_id: str
    ) -> aiosqlite.Row | None:
        """Return the most recent completed classification for a message."""
        assert self._db
        async with self._db.execute(
            """
            SELECT cm.* FROM classified_messages cm
            JOIN runs r ON cm.run_id = r.id
            WHERE cm.id = ? AND r.status = ?
            ORDER BY cm.classified_at DESC
            LIMIT 1
            """,
            (message_id, RunStatus.COMPLETE),
        ) as cur:
            return await cur.fetchone()

    # --- feedback ---

    async def record_feedback(
        self,
        message_id: str,
        run_id: str,
        old_category: str,
        new_category: str,
        vote: str,
        note: str | None = None,
    ) -> None:
        """Record a user correction for a triaged message.

        vote: 'correct' | 'wrong' | 'snooze'
        """
        assert self._db
        await self._db.execute(
            """
            INSERT INTO feedback
                (message_id, run_id, old_category, new_category, vote, note, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (message_id, run_id, old_category, new_category, vote, note, _now_iso()),
        )
        await self._db.commit()

    async def get_feedback_for_message(
        self, message_id: str
    ) -> list[aiosqlite.Row]:
        assert self._db
        async with self._db.execute(
            "SELECT * FROM feedback WHERE message_id = ? ORDER BY recorded_at DESC",
            (message_id,),
        ) as cur:
            return await cur.fetchall()

    async def get_recent_wrong_votes(
        self, limit: int = 50
    ) -> list[aiosqlite.Row]:
        """Return recent 'wrong' votes — useful for rule review and fine-tuning."""
        assert self._db
        async with self._db.execute(
            """
            SELECT * FROM feedback WHERE vote = 'wrong'
            ORDER BY recorded_at DESC LIMIT ?
            """,
            (limit,),
        ) as cur:
            return await cur.fetchall()

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
