"""Playwright page adapter — puppeteer-stealth style automation API."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from playwright.async_api import BrowserContext, ElementHandle, Page

from capsolver.core.logging import get_logger

logger = get_logger(__name__)


class AutomationTimeout(Exception):
    """Navigation or action timed out."""


def _extract_has_text(selector: str) -> str | None:
    m = re.search(r':has-text\("([^"]+)"\)', selector)
    return m.group(1) if m else None


class PlaywrightElementAdapter:
    def __init__(self, handle: ElementHandle):
        self._handle = handle

    async def get_attribute(self, name: str) -> str | None:
        return await self._handle.get_attribute(name)


class PlaywrightLocatorAdapter:
    def __init__(self, page: "PlaywrightPageAdapter", selector: str):
        self._page = page
        self._selector = selector

    async def count(self) -> int:
        text = _extract_has_text(self._selector)
        if text:
            loc = self._page._page.get_by_text(text, exact=False)
            return await loc.count()
        return await self._page._page.locator(self._selector).count()

    async def wait_for(self, state: str = "visible", timeout: int = 10000) -> None:
        loc = self._page._page.locator(self._selector)
        if state == "visible":
            await loc.first.wait_for(state="visible", timeout=timeout)
        else:
            await loc.first.wait_for(timeout=timeout)

    async def click(self, timeout: int = 10000) -> None:
        text = _extract_has_text(self._selector)
        if text:
            await self._page._page.get_by_text(text, exact=False).first.click(timeout=timeout)
            return
        await self._page._page.locator(self._selector).first.click(timeout=timeout)


class PlaywrightContextAdapter:
    def __init__(self, context: BrowserContext):
        self._context = context

    async def cookies(self, urls: str | None = None) -> list[dict[str, Any]]:
        if urls:
            return await self._context.cookies(urls)
        return await self._context.cookies()


class PlaywrightPageAdapter:
    """Thin wrapper matching automation expectations."""

    def __init__(self, page: Page, context: BrowserContext):
        self._page = page
        self._context = context
        self.context = PlaywrightContextAdapter(context)

    @property
    def url(self) -> str:
        return self._page.url

    async def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 60000) -> None:
        try:
            await self._page.goto(url, wait_until=wait_until, timeout=timeout)
        except Exception as e:
            if "Timeout" in type(e).__name__:
                raise AutomationTimeout(str(e)) from e
            raise

    async def reload(self, wait_until: str = "domcontentloaded", timeout: int = 60000) -> None:
        await self._page.reload(wait_until=wait_until, timeout=timeout)

    async def click_by_text(self, text: str, timeout: float = 10) -> bool:
        try:
            await self._page.get_by_text(text, exact=False).first.click(timeout=timeout * 1000)
            return True
        except Exception:
            return False

    async def evaluate(self, expression: str, arg: Any = None) -> Any:
        if arg is not None:
            return await self._page.evaluate(expression, arg)
        return await self._page.evaluate(expression)

    async def query_selector(self, selector: str) -> PlaywrightElementAdapter | None:
        handle = await self._page.query_selector(selector)
        return PlaywrightElementAdapter(handle) if handle else None

    async def content(self) -> str:
        return await self._page.content()

    async def inner_text(self, selector: str) -> str:
        if selector == "body":
            return await self._page.inner_text("body")
        el = await self._page.query_selector(selector)
        if el:
            return (await el.inner_text()) or ""
        return ""

    def locator(self, selector: str) -> PlaywrightLocatorAdapter:
        return PlaywrightLocatorAdapter(self, selector)

    async def screenshot(self, path: str, full_page: bool = True) -> None:
        await self._page.screenshot(path=path, full_page=full_page)

    async def wait_for_url(self, pattern: str, timeout: int = 60000) -> None:
        needle = pattern.replace("**", "").strip()
        try:
            await self._page.wait_for_url(f"*{needle}*", timeout=timeout)
        except Exception as e:
            raise AutomationTimeout(str(e)) from e

    async def bring_to_front(self) -> None:
        await self._page.bring_to_front()
