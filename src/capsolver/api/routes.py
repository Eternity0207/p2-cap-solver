"""FastAPI route handlers."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from fastapi.security import APIKeyHeader

from capsolver import __version__
from capsolver.api.schemas import (
    CreateJobRequest,
    ErrorResponse,
    HealthResponse,
    JobListResponse,
    JobResponse,
    StatsResponse,
    VerifyRequest,
    VerifyResponse,
)
from capsolver.core.config import get_config
from capsolver.core.platform import detect_platform
from capsolver.jobs.manager import JobManager
from capsolver.jobs.models import Job, JobRequest, JobStatus, JobType

router = APIRouter()
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

_manager: JobManager | None = None


def get_manager() -> JobManager:
    if _manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return _manager


def set_manager(manager: JobManager) -> None:
    global _manager
    _manager = manager


async def verify_api_key(
    api_key: Annotated[str | None, Security(api_key_header)] = None,
) -> None:
    config = get_config()
    if config.server.api_key and api_key != config.server.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


def _job_to_response(job: Job) -> JobResponse:
    data = job.to_public_dict()
    return JobResponse.model_validate(data)


def _job_to_verify_response(job: Job) -> VerifyResponse:
    result = job.result
    return VerifyResponse(
        job_id=job.id,
        status=job.status,
        success=bool(result.success) if result else False,
        verified=bool(result.verified) if result else False,
        final_url=result.final_url if result else None,
        error=result.error if result else None,
        attempts=result.attempts if result else job.attempt,
        duration_seconds=result.duration_seconds if result else 0.0,
    )


async def _wait_for_terminal_status(
    manager: JobManager,
    job_id: str,
    timeout_seconds: int,
) -> Job | None:
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    terminal = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
    while asyncio.get_event_loop().time() < deadline:
        job = await manager.get_job(job_id)
        if not job:
            return None
        if job.status in terminal:
            return job
        await asyncio.sleep(1)
    return await manager.get_job(job_id)


@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health() -> HealthResponse:
    platform = detect_platform()
    return HealthResponse(
        status="healthy",
        version=__version__,
        platform={
            "os": platform.os_type.value,
            "distro": platform.distro,
            "arch": platform.arch,
            "has_display": platform.has_display,
            "xvfb_available": platform.xvfb_available,
        },
    )


@router.get(
    "/stats",
    response_model=StatsResponse,
    tags=["System"],
    dependencies=[Depends(verify_api_key)],
)
async def stats(manager: JobManager = Depends(get_manager)) -> StatsResponse:
    data = await manager.get_stats()
    return StatsResponse(version=__version__, **data)


@router.post(
    "/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Jobs"],
    dependencies=[Depends(verify_api_key)],
    responses={400: {"model": ErrorResponse}},
)
async def create_job(
    request: CreateJobRequest,
    manager: JobManager = Depends(get_manager),
) -> JobResponse:
    job_request = JobRequest(
        url=request.url,
        discord_token=request.discord_token,
        job_type=request.job_type,
        max_retries=request.max_retries,
        metadata=request.metadata,
    )
    job = await manager.create_job(job_request)
    return _job_to_response(job)


@router.post(
    "/verify",
    response_model=VerifyResponse,
    tags=["Jobs"],
    dependencies=[Depends(verify_api_key)],
    responses={400: {"model": ErrorResponse}},
)
async def verify_link_with_token(
    request: VerifyRequest,
    wait: int = Query(0, ge=0, le=3600, description="Seconds to wait for completion"),
    manager: JobManager = Depends(get_manager),
) -> VerifyResponse:
    job_request = JobRequest(
        url=request.link,
        discord_token=request.token,
        job_type=JobType.POKETWO_VERIFY,
        max_retries=request.max_retries,
        metadata=request.metadata,
    )
    job = await manager.create_job(job_request)
    if wait <= 0:
        return _job_to_verify_response(job)

    finished = await _wait_for_terminal_status(manager, job.id, timeout_seconds=wait)
    if not finished:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_verify_response(finished)


@router.get(
    "/jobs",
    response_model=JobListResponse,
    tags=["Jobs"],
    dependencies=[Depends(verify_api_key)],
)
async def list_jobs(
    status_filter: JobStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    manager: JobManager = Depends(get_manager),
) -> JobListResponse:
    jobs = await manager.list_jobs(status=status_filter, limit=limit, offset=offset)
    return JobListResponse(
        jobs=[_job_to_response(j) for j in jobs],
        total=len(jobs),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    tags=["Jobs"],
    dependencies=[Depends(verify_api_key)],
)
async def get_job(
    job_id: str,
    manager: JobManager = Depends(get_manager),
) -> JobResponse:
    job = await manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_response(job)


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=JobResponse,
    tags=["Jobs"],
    dependencies=[Depends(verify_api_key)],
)
async def cancel_job(
    job_id: str,
    manager: JobManager = Depends(get_manager),
) -> JobResponse:
    job = await manager.cancel_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_response(job)


@router.get(
    "/jobs/{job_id}/screenshots/{filename}",
    tags=["Jobs"],
    dependencies=[Depends(verify_api_key)],
)
async def get_screenshot(job_id: str, filename: str):
    from fastapi.responses import FileResponse

    config = get_config()
    artifacts_dir = config.resolve_path(config.jobs.artifacts_dir) / job_id
    path = artifacts_dir / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    # Prevent path traversal
    if not str(path.resolve()).startswith(str(artifacts_dir.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")
    return FileResponse(path, media_type="image/png")


@router.get(
    "/jobs/{job_id}/report",
    tags=["Jobs"],
    dependencies=[Depends(verify_api_key)],
)
async def get_job_report(
    job_id: str,
    manager: JobManager = Depends(get_manager),
):
    job = await manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    config = get_config()
    artifacts_dir = config.resolve_path(config.jobs.artifacts_dir) / job_id

    return {
        "job": job.to_public_dict(),
        "report": {
            "summary": {
                "success": job.result.success if job.result else False,
                "verified": job.result.verified if job.result else False,
                "attempts": job.attempt,
                "duration_seconds": job.result.duration_seconds if job.result else 0,
            },
            "steps": [
                {"step": log.step, "message": log.message, "level": log.level, "time": log.timestamp}
                for log in job.logs
            ],
            "screenshots": job.result.screenshots if job.result else [],
            "artifacts_dir": str(artifacts_dir),
        },
    }


@router.post(
    "/admin/cleanup",
    tags=["Admin"],
    dependencies=[Depends(verify_api_key)],
)
async def cleanup_jobs(manager: JobManager = Depends(get_manager)) -> dict:
    deleted = await manager.cleanup_old_jobs()
    return {"deleted_jobs": deleted}
