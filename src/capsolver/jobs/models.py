"""Job models and persistence."""

from __future__ import annotations

import enum
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_CAPTCHA = "waiting_captcha"
    WAITING_DISCORD = "waiting_discord"
    WAITING_AUTHORIZE = "waiting_authorize"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class JobType(str, enum.Enum):
    POKETWO_VERIFY = "poketwo_verify"


class LogEntry(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    level: str = "info"
    step: str = ""
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class JobProgress(BaseModel):
    current_step: str = ""
    percent: int = 0
    message: str = ""


class JobRequest(BaseModel):
    url: HttpUrl
    discord_token: str
    job_type: JobType = JobType.POKETWO_VERIFY
    max_retries: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobResult(BaseModel):
    success: bool = False
    verified: bool = False
    final_url: str | None = None
    screenshots: list[str] = Field(default_factory=list)
    error: str | None = None
    attempts: int = 0
    duration_seconds: float = 0.0


class Job(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.PENDING
    job_type: JobType = JobType.POKETWO_VERIFY
    url: str = ""
    discord_token: str = ""  # Never expose in API responses
    max_retries: int = 3
    attempt: int = 0
    progress: JobProgress = Field(default_factory=JobProgress)
    logs: list[LogEntry] = Field(default_factory=list)
    result: JobResult | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def add_log(self, step: str, message: str, level: str = "info", **data: Any) -> LogEntry:
        entry = LogEntry(step=step, message=message, level=level, data=data)
        self.logs.append(entry)
        self.updated_at = datetime.now(timezone.utc)
        return entry

    def update_progress(self, step: str, percent: int, message: str = "") -> None:
        self.progress = JobProgress(current_step=step, percent=percent, message=message)
        self.updated_at = datetime.now(timezone.utc)

    def to_public_dict(self) -> dict[str, Any]:
        """Serialize for API (excludes sensitive token)."""
        data = self.model_dump(mode="json")
        data.pop("discord_token", None)
        return data

    def to_storage_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
