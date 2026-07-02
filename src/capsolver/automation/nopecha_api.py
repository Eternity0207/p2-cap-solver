"""NopeCHA Token API client for Turnstile solving."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from capsolver.core.logging import get_logger

logger = get_logger(__name__)

API_URL = "https://api.nopecha.com/token/"


class NopechaAPIError(Exception):
    pass


async def solve_turnstile(
    api_key: str,
    sitekey: str,
    url: str,
    *,
    timeout_seconds: int = 120,
    poll_interval: float = 2.0,
) -> str:
    """Solve Cloudflare Turnstile via NopeCHA Token API."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload: dict[str, Any] = {
            "key": api_key,
            "type": "turnstile",
            "sitekey": sitekey,
            "url": url,
        }
        logger.info("nopecha_submit", sitekey=sitekey[:12], url=url)
        resp = await client.post(API_URL, json=payload)
        data = resp.json()

        if resp.status_code != 200 or "data" not in data:
            raise NopechaAPIError(f"NopeCHA submit failed: {data}")

        job_id = data["data"]
        logger.info("nopecha_job_created", job_id=job_id)

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            await asyncio.sleep(poll_interval)
            poll = await client.get(API_URL, params={"key": api_key, "id": job_id})
            result = poll.json()

            if poll.status_code == 200 and isinstance(result.get("data"), str):
                token = result["data"]
                if len(token) > 10:
                    logger.info("nopecha_solved", job_id=job_id)
                    return token

            if result.get("error") == 14:
                # Still processing
                continue

            if "error" in result and result.get("error") != 14:
                raise NopechaAPIError(f"NopeCHA poll error: {result}")

        raise NopechaAPIError("NopeCHA solve timeout")
