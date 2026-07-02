"""Cloudflare cookie helpers."""

from __future__ import annotations

from capsolver.browser.page_adapter import BrowserContextAdapter, PageAdapter


async def has_cf_clearance(context: BrowserContextAdapter, domain: str = "verify.poketwo.net") -> bool:
    cookies = await context.cookies(f"https://{domain}")
    return any(c.get("name") == "cf_clearance" for c in cookies)
