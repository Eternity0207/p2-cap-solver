"""API request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl

from capsolver.jobs.models import JobProgress, JobStatus, JobType, LogEntry


class CreateJobRequest(BaseModel):
    url: HttpUrl
    discord_token: str = Field(..., min_length=10, description="Discord user token")
    job_type: JobType = JobType.POKETWO_VERIFY
    max_retries: int | None = Field(None, ge=0, le=10)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VerifyRequest(BaseModel):
    link: HttpUrl = Field(..., description="Poketwo verification URL")
    token: str = Field(..., min_length=10, description="Discord user token")
    max_retries: int | None = Field(None, ge=0, le=10)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VerifyResponse(BaseModel):
    job_id: str
    status: JobStatus
    success: bool
    verified: bool
    final_url: str | None = None
    error: str | None = None
    attempts: int = 0
    duration_seconds: float = 0.0


class JobResponse(BaseModel):
    id: str
    status: JobStatus
    job_type: JobType
    url: str
    attempt: int
    max_retries: int
    progress: JobProgress
    logs: list[LogEntry]
    result: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int
    limit: int
    offset: int


class StatsResponse(BaseModel):
    queue_size: int
    active_browsers: int
    max_concurrent: int
    jobs_by_status: dict[str, int]
    version: str


class HealthResponse(BaseModel):
    status: str
    version: str
    platform: dict[str, Any]


class ErrorResponse(BaseModel):
    detail: str
    code: str | None = None
