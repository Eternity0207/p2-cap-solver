"""Configure the NopeCHA extension by importing settings via its setup page.

NopeCHA reads the API key from the URL *hash* (``https://nopecha.com/setup#KEY``),
not a query string. Visiting that URL makes the extension's content script store
the key, after which it auto-solves captchas on any page.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from capsolver.core.logging import get_logger

logger = get_logger(__name__)

SETUP_URL = "https://nopecha.com/setup#{key}"


def read_nopecha_key(fallback: str = "") -> str:
    return os.getenv("NOPECHA_API_KEY", "").strip() or fallback.strip()


async def inject_key(browser_or_page: Any, key: str, return_url: str | None = None) -> bool:
    """Store the NopeCHA API key once at browser startup (before Poketwo)."""
    if not key:
        logger.warning("nopecha_key_missing")
        return False

    tab = _tab(browser_or_page)
    if tab is None:
        return False

    # Give the freshly-loaded extension's service worker time to register.
    await asyncio.sleep(6)

    url = SETUP_URL.format(key=key)
    ok = False
    for attempt in range(4):
        try:
            await tab.get(url)
            await tab
            await asyncio.sleep(3)

            body = str(await tab.evaluate("document.body ? document.body.innerText : ''")).lower()
            if "imported settings" in body and key.lower() in body:
                logger.info("nopecha_key_injected")
                ok = True
                break
            if "extension is required" in body:
                logger.warning("nopecha_setup_no_ext", attempt=attempt + 1)
            else:
                logger.warning("nopecha_setup_unexpected", attempt=attempt + 1, body=body[:80])
            await asyncio.sleep(3)
        except Exception as e:
            logger.warning("nopecha_inject_failed", attempt=attempt + 1, error=str(e))
            await asyncio.sleep(2)

    if not ok:
        logger.error("nopecha_key_not_set")

    if return_url:
        try:
            await tab.get(return_url)
            await tab
        except Exception:
            pass
    return ok


def _tab(browser_or_page: Any) -> Any:
    if hasattr(browser_or_page, "main_tab"):
        return browser_or_page.main_tab
    if hasattr(browser_or_page, "_tab"):
        return browser_or_page._tab
    return browser_or_page
