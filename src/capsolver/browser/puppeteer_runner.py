"""Run Poketwo automation via puppeteer-extra + stealth (Node, bundled Chromium)."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from capsolver.core.config import AppConfig, get_config
from capsolver.core.logging import get_logger
from capsolver.jobs.models import Job

logger = get_logger(__name__)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "puppeteer-poketwo.mjs"
ROOT = SCRIPT.parent.parent


async def run_puppeteer_job(
    job: Job,
    artifacts_dir: Path,
    config: AppConfig | None = None,
    on_progress: Any = None,
) -> bool:
    config = config or get_config()
    sid = str(uuid.uuid4())
    profile_dir = config.resolve_path(config.browser.user_data_base) / "temp" / sid
    profile_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "url": job.url,
        "discordToken": job.discord_token,
        "nopechaApiKey": config.automation.poketwo.captcha.nopecha_api_key,
        "artifactsDir": str(artifacts_dir),
        "profileDir": str(profile_dir),
    }

    env = {**os.environ}
    env.setdefault("DISPLAY", ":0")

    logger.info("puppeteer_stealth_start", url=job.url, profile=str(profile_dir))

    proc = await asyncio.create_subprocess_exec(
        "node",
        str(SCRIPT),
        json.dumps(payload),
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate()

    if stderr:
        for line in stderr.decode(errors="replace").strip().splitlines()[-30:]:
            logger.info("puppeteer_stderr", line=line)

    try:
        result = json.loads(stdout.decode() or "{}")
    except json.JSONDecodeError:
        job.add_log("error", f"Puppeteer invalid output: {stdout.decode()[:500]}", level="error")
        _cleanup_profile(profile_dir, False)
        return False

    for entry in result.get("logs", []):
        job.add_log(entry.get("step", "puppeteer"), entry.get("message", ""), level=entry.get("level", "info"))
        if on_progress and entry.get("step"):
            pct = _step_percent(entry.get("step", ""))
            await on_progress(entry["step"], pct, entry.get("message", ""))

    if job.result:
        job.result.screenshots = result.get("screenshots", [])
        job.result.verified = result.get("success", False)
        if result.get("error"):
            job.result.error = result["error"]

    success = bool(result.get("success"))
    if success:
        logger.info("puppeteer_stealth_success", job_id=job.id)
    else:
        logger.warning("puppeteer_stealth_failed", job_id=job.id, error=result.get("error"))
        _cleanup_profile(profile_dir, False)

    return success


def _cleanup_profile(profile_dir: Path, already_deleted: bool) -> None:
    if not already_deleted and profile_dir.exists():
        shutil.rmtree(profile_dir, ignore_errors=True)


def _step_percent(step: str) -> int:
    return {
        "launch": 5,
        "nopecha": 10,
        "navigate": 15,
        "captcha": 30,
        "verify_click": 50,
        "discord_redirect": 55,
        "discord_login": 65,
        "authorize": 75,
        "verify_result": 85,
        "complete": 100,
    }.get(step, 50)
