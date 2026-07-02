"""Basic tests for Cap-Solver."""

import pytest
from capsolver.core.config import load_config, AppConfig
from capsolver.jobs.models import Job, JobRequest, JobStatus, JobType


def test_load_config():
    config = load_config("config/default.yaml")
    assert isinstance(config, AppConfig)
    assert config.server.port == 8080
    assert config.browser.max_concurrent >= 1


def test_job_model():
    job = Job(url="https://verify.poketwo.net/captcha/123", discord_token="test_token_12345")
    public = job.to_public_dict()
    assert "discord_token" not in public
    assert job.status == JobStatus.PENDING


def test_job_request():
    req = JobRequest(
        url="https://verify.poketwo.net/captcha/123",
        discord_token="test_token_12345",
    )
    assert req.job_type == JobType.POKETWO_VERIFY
