"""Job persistence layer."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from capsolver.core.config import get_config
from capsolver.core.logging import get_logger
from capsolver.jobs.models import Job, JobStatus

logger = get_logger(__name__)


class JobStore:
    """SQLite-backed job storage."""

    def __init__(self, db_path: str | None = None):
        config = get_config()
        self.db_path = Path(db_path or config.jobs.store_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)"
        )
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)"
        )
        await self._db.commit()
        logger.info("job_store_connected", path=str(self.db_path))

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def save(self, job: Job) -> None:
        assert self._db is not None
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """
            INSERT INTO jobs (id, status, data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                data = excluded.data,
                updated_at = excluded.updated_at
            """,
            (
                job.id,
                job.status.value,
                json.dumps(job.to_storage_dict()),
                job.created_at.isoformat(),
                now,
            ),
        )
        await self._db.commit()

    async def get(self, job_id: str) -> Job | None:
        assert self._db is not None
        async with self._db.execute(
            "SELECT data FROM jobs WHERE id = ?", (job_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return Job.model_validate(json.loads(row["data"]))

    async def list_jobs(
        self,
        status: JobStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        assert self._db is not None
        if status:
            query = (
                "SELECT data FROM jobs WHERE status = ? "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?"
            )
            params: tuple[Any, ...] = (status.value, limit, offset)
        else:
            query = "SELECT data FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params = (limit, offset)

        jobs: list[Job] = []
        async with self._db.execute(query, params) as cursor:
            async for row in cursor:
                jobs.append(Job.model_validate(json.loads(row["data"])))
        return jobs

    async def count_by_status(self) -> dict[str, int]:
        assert self._db is not None
        counts: dict[str, int] = {}
        async with self._db.execute(
            "SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status"
        ) as cursor:
            async for row in cursor:
                counts[row["status"]] = row["cnt"]
        return counts

    async def cleanup_old(self, hours: int) -> int:
        assert self._db is not None
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        async with self._db.execute(
            "DELETE FROM jobs WHERE created_at < ? AND status IN (?, ?, ?)",
            (cutoff, JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value),
        ) as cursor:
            await self._db.commit()
            return cursor.rowcount
