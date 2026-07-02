"""Cloudflare bypass — wait until Poketwo verify page is reachable."""

from __future__ import annotations

import asyncio

from capsolver.browser.page_adapter import PageAdapter
from capsolver.core.config import CloudflareConfig, get_config
from capsolver.core.logging import get_logger
from capsolver.jobs.models import Job

logger = get_logger(__name__)

CF_PAGE_MARKERS = (
    "performing security verification",
    "verifying you are human",
    "just a moment",
    "checking your browser",
    "security service to protect",
    "this may take a few seconds",
    "ray id:",
)


async def page_body_text(page: PageAdapter) -> str:
    try:
        return (await page.inner_text("body")).lower()
    except Exception:
        return ""


async def is_past_cloudflare(page: PageAdapter) -> bool:
    # The URL is the same during the Cloudflare interstitial and the hCaptcha
    # page, so we must judge by page content, not the URL.
    text = await page_body_text(page)
    if not text:
        return False
    if any(m in text for m in CF_PAGE_MARKERS):
        return False
    if any(k in text for k in ("please verify", "i am human", "hcaptcha", "complete the captcha")):
        return True
    # hCaptcha widget present but no CF markers -> past Cloudflare.
    return await page.locator('[data-hcaptcha-widget-id], iframe[src*="hcaptcha.com"]').count() > 0


class CloudflareBypass:
    def __init__(self, config: CloudflareConfig | None = None):
        self.config = config or get_config().automation.poketwo.cloudflare

    async def wait_until_clear(self, page: PageAdapter, job: Job) -> bool:
        max_wait = self.config.max_wait_seconds
        elapsed = 0
        job.add_log("cloudflare", "Waiting for Poketwo page")

        while elapsed < max_wait:
            if await is_past_cloudflare(page):
                job.add_log("cloudflare", "Poketwo verify page loaded")
                return True

            if elapsed > 0 and elapsed % 30 == 0:
                job.add_log("cloudflare", f"Still waiting ({elapsed}s)")

            await asyncio.sleep(2)
            elapsed += 2

        job.add_log("cloudflare", f"Timed out after {max_wait}s", level="error")
        return False
