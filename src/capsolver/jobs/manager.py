"""Job queue and execution manager."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

from capsolver.automation.poketwo import PoketwoAutomation
from capsolver.browser.session import BrowserPool
from capsolver.core.config import get_config
from capsolver.core.logging import get_logger
from capsolver.jobs.models import Job, JobRequest, JobResult, JobStatus, JobType
from capsolver.jobs.store import JobStore

logger = get_logger(__name__)

JobUpdateCallback = Callable[[Job], Awaitable[None]]


class JobManager:
    """Orchestrates job queue, execution, retries, and cleanup."""

    def __init__(
        self,
        store: JobStore | None = None,
        pool: BrowserPool | None = None,
    ):
        self.config = get_config()
        self.store = store or JobStore()
        self.pool = pool or BrowserPool()
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._subscribers: dict[str, list[JobUpdateCallback]] = {}
        self._global_subscribers: list[JobUpdateCallback] = []
        self._running = False
        self._active_jobs: dict[str, asyncio.Task] = {}
        self._automations = {
            JobType.POKETWO_VERIFY: PoketwoAutomation(),
        }

    async def start(self, worker_count: int | None = None) -> None:
        await self.store.connect()
        self._running = True
        count = worker_count or self.config.browser.max_concurrent
        for i in range(count):
            task = asyncio.create_task(self._worker_loop(i), name=f"job-worker-{i}")
            self._workers.append(task)
        logger.info("job_manager_started", workers=count)

    async def stop(self) -> None:
        self._running = False
        for task in self._workers:
            task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

        for job_id, task in list(self._active_jobs.items()):
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._active_jobs.clear()

        await self.pool.shutdown()
        await self.store.close()
        logger.info("job_manager_stopped")

    def subscribe(self, job_id: str, callback: JobUpdateCallback) -> None:
        self._subscribers.setdefault(job_id, []).append(callback)

    def unsubscribe(self, job_id: str, callback: JobUpdateCallback) -> None:
        if job_id in self._subscribers:
            self._subscribers[job_id] = [c for c in self._subscribers[job_id] if c != callback]

    def subscribe_all(self, callback: JobUpdateCallback) -> None:
        self._global_subscribers.append(callback)

    async def _notify(self, job: Job) -> None:
        await self.store.save(job)
        for cb in self._subscribers.get(job.id, []):
            try:
                await cb(job)
            except Exception as e:
                logger.warning("subscriber_error", job_id=job.id, error=str(e))
        for cb in self._global_subscribers:
            try:
                await cb(job)
            except Exception as e:
                logger.warning("global_subscriber_error", error=str(e))

    async def create_job(self, request: JobRequest) -> Job:
        job = Job(
            url=str(request.url),
            discord_token=request.discord_token,
            job_type=request.job_type,
            max_retries=request.max_retries or self.config.jobs.max_retries,
            metadata=request.metadata,
            status=JobStatus.QUEUED,
            result=JobResult(),
        )
        job.add_log("created", f"Job queued for {job.url}")
        await self.store.save(job)
        await self._queue.put(job.id)
        await self._notify(job)
        logger.info("job_created", job_id=job.id, url=job.url)
        return job

    async def get_job(self, job_id: str) -> Job | None:
        return await self.store.get(job_id)

    async def cancel_job(self, job_id: str) -> Job | None:
        job = await self.store.get(job_id)
        if not job:
            return None
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            return job
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now(timezone.utc)
        job.add_log("cancelled", "Job cancelled by user")
        await self._notify(job)

        if job_id in self._active_jobs:
            self._active_jobs[job_id].cancel()
        return job

    async def list_jobs(
        self,
        status: JobStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        return await self.store.list_jobs(status=status, limit=limit, offset=offset)

    async def get_stats(self) -> dict[str, Any]:
        counts = await self.store.count_by_status()
        return {
            "queue_size": self._queue.qsize(),
            "active_browsers": self.pool.active_count,
            "max_concurrent": self.pool.max_concurrent,
            "jobs_by_status": counts,
        }

    async def cleanup_old_jobs(self) -> int:
        return await self.store.cleanup_old(self.config.jobs.cleanup_after_hours)

    async def _worker_loop(self, worker_id: int) -> None:
        logger.info("worker_started", worker_id=worker_id)
        while self._running:
            try:
                job_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            job = await self.store.get(job_id)
            if not job or job.status == JobStatus.CANCELLED:
                self._queue.task_done()
                continue

            task = asyncio.create_task(self._execute_job(job))
            self._active_jobs[job_id] = task
            try:
                await task
            except asyncio.CancelledError:
                pass
            finally:
                self._active_jobs.pop(job_id, None)
                self._queue.task_done()

    async def _execute_job(self, job: Job) -> None:
        start = datetime.now(timezone.utc)
        job.started_at = start
        job.status = JobStatus.RUNNING
        automation = self._automations.get(job.job_type)
        if not automation:
            job.status = JobStatus.FAILED
            job.result = job.result or JobResult()
            job.result.error = f"Unknown job type: {job.job_type}"
            job.completed_at = datetime.now(timezone.utc)
            await self._notify(job)
            return

        max_attempts = job.max_retries + 1
        success = False

        for attempt in range(1, max_attempts + 1):
            job.attempt = attempt
            if attempt > 1:
                job.status = JobStatus.RETRYING
                job.add_log("retry", f"Attempt {attempt}/{max_attempts}")
                await self._notify(job)
                await asyncio.sleep(self.config.jobs.retry_delay_seconds)

            # Check cancellation
            current = await self.store.get(job.id)
            if current and current.status == JobStatus.CANCELLED:
                return

            session = None
            try:
                async def on_progress(step: str, pct: int, msg: str) -> None:
                    job.update_progress(step, pct, msg)
                    await self._notify(job)

                session = await self.pool.acquire(job.id, job.id)

                success = await asyncio.wait_for(
                    automation.execute(job, session, on_progress=on_progress),
                    timeout=self.config.browser.job_timeout_seconds,
                )

                if success:
                    break

            except asyncio.TimeoutError:
                job.add_log("timeout", "Job exceeded timeout", level="error")
            except Exception as e:
                job.add_log("error", str(e), level="error")
                logger.exception("job_execution_error", job_id=job.id, attempt=attempt)
            finally:
                if session:
                    await self.pool.release(session, cleanup_profile=True)

        end = datetime.now(timezone.utc)
        duration = (end - start).total_seconds()

        job.result = job.result or JobResult()
        job.result.success = success
        job.result.verified = success
        job.result.attempts = job.attempt
        job.result.duration_seconds = duration
        job.completed_at = end

        if success:
            job.status = JobStatus.COMPLETED
            job.add_log("completed", "Verification successful")
        else:
            job.status = JobStatus.FAILED
            job.result.error = job.result.error or "Verification failed after all retries"
            job.add_log("failed", job.result.error, level="error")

        await self._notify(job)
        logger.info(
            "job_finished",
            job_id=job.id,
            success=success,
            attempts=job.attempt,
            duration=duration,
        )
