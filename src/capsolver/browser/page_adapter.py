"""Playwright-like adapter over zendriver Tab (undetected / nodriver family)."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import zendriver as zd

from capsolver.core.logging import get_logger

logger = get_logger(__name__)


class AutomationTimeout(Exception):
    """Navigation or action timed out."""


class LocatorAdapter:
    def __init__(self, page: "PageAdapter", selector: str):
        self._page = page
        self._selector = selector

    async def count(self) -> int:
        text = _extract_has_text(self._selector)
        if text:
            try:
                elems = await self._page._tab.find_elements_by_text(text, best_match=True)
                return len(elems)
            except Exception:
                return 0
        try:
            elems = await self._page._tab.query_selector_all(self._selector)
            return len(elems)
        except Exception:
            return 0

    async def wait_for(self, state: str = "visible", timeout: int = 10000) -> None:
        if state != "visible":
            return
        deadline = asyncio.get_event_loop().time() + timeout / 1000
        while asyncio.get_event_loop().time() < deadline:
            if await self.count() > 0:
                return
            await asyncio.sleep(0.3)
        raise AutomationTimeout(f"Locator not visible: {self._selector}")

    async def click(self, timeout: int = 10000) -> None:
        await self.wait_for(timeout=timeout)
        text = _extract_has_text(self._selector)
        if text:
            el = await self._page._tab.find_element_by_text(text, best_match=True)
            await el.click()
            return
        el = await self._page._tab.select(self._selector, timeout=timeout / 1000)
        await el.click()


def _extract_has_text(selector: str) -> str | None:
    m = re.search(r':has-text\("([^"]+)"\)', selector)
    return m.group(1) if m else None


def _is_js_function(expr: str) -> bool:
    """True if the JS source is a function that must be called (IIFE-wrapped)."""
    s = expr.lstrip()
    if s.startswith(("function", "async function")):
        return True
    # arrow function: starts with params list and has =>
    return s.startswith("(") and "=>" in s.split("{", 1)[0]


class BrowserContextAdapter:
    """Minimal context wrapper for cookie access."""

    def __init__(self, browser: zd.Browser):
        self._browser = browser

    async def cookies(self, urls: str | None = None) -> list[dict[str, Any]]:
        raw = await self._browser.cookies.get_all()
        result = []
        for c in raw:
            d = c.domain or ""
            if urls and urls not in d and not d.endswith(urls.replace("https://", "")):
                continue
            result.append({"name": c.name, "value": c.value, "domain": c.domain})
        return result


class PageAdapter:
    """Thin API compatible with existing automation code."""

    def __init__(self, browser: zd.Browser, tab: zd.Tab):
        self._browser = browser
        self._tab = tab
        self.context = BrowserContextAdapter(browser)

    @property
    def url(self) -> str:
        try:
            return self._tab.url or ""
        except Exception:
            return ""

    async def current_url(self) -> str:
        try:
            await self._tab
            return self._tab.url or ""
        except Exception:
            return await self._find_url_in_tabs()

    async def _find_url_in_tabs(self) -> str:
        for tab in self._browser.tabs:
            try:
                u = tab.url or ""
                if u and u not in ("about:blank", ""):
                    self._tab = tab
                    return u
            except Exception:
                continue
        return ""

    async def wait_for_url(self, pattern: str, timeout: int = 60000) -> None:
        needle = pattern.replace("**", "").strip()
        deadline = asyncio.get_event_loop().time() + timeout / 1000
        while asyncio.get_event_loop().time() < deadline:
            url = await self.current_url()
            if needle in url:
                return
            await asyncio.sleep(0.5)
        raise AutomationTimeout(f"URL pattern not matched: {pattern}")

    async def safe_evaluate(self, expression: str, arg: Any = None) -> Any:
        try:
            return await self.evaluate(expression, arg)
        except Exception as e:
            logger.debug("evaluate_failed", error=str(e))
            return None

    async def click_verify(self) -> bool:
        """Click Poketwo Verify using real mouse coordinates."""
        coords = await self.safe_evaluate(
            """() => {
                const nodes = document.querySelectorAll(
                    'button, input[type="submit"], input[type="button"], a, [role="button"]'
                );
                for (const el of nodes) {
                    const label = (el.innerText || el.textContent || el.value || '').replace(/\\s+/g, ' ').trim();
                    if (!/\\bverify\\b/i.test(label)) continue;
                    if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                    el.scrollIntoView({ block: 'center' });
                    const r = el.getBoundingClientRect();
                    if (r.width < 2 || r.height < 2) continue;
                    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
                }
                return null;
            }"""
        )
        if coords and isinstance(coords, dict):
            try:
                await self._tab.mouse_click(float(coords["x"]), float(coords["y"]))
                return True
            except Exception as e:
                logger.debug("mouse_click_verify_failed", error=str(e))

        try:
            el = await self._tab.find_element_by_text("Verify", best_match=True)
            if el:
                await el.scroll_into_view()
                await el.mouse_click()
                return True
        except Exception:
            pass

        try:
            el = await self._tab.find("Verify", timeout=3)
            await el.scroll_into_view()
            await el.click()
            return True
        except Exception:
            return False

    async def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 60000) -> None:
        try:
            if self._tab.url in (None, "", "about:blank"):
                await self._browser.get(url)
            else:
                await self._tab.get(url)
            await self._tab
            await self._browser.sleep(1)
        except asyncio.TimeoutError as e:
            raise AutomationTimeout(str(e)) from e
        except Exception as e:
            if "Timeout" in type(e).__name__:
                raise AutomationTimeout(str(e)) from e
            raise

    async def reload(self, wait_until: str = "domcontentloaded", timeout: int = 60000) -> None:
        await self._tab.reload()
        await self._tab
        await self._browser.sleep(1)

    async def click_by_text(self, text: str, timeout: float = 10) -> bool:
        try:
            el = await self._tab.find(text, timeout=timeout)
            await el.click()
            return True
        except Exception:
            return False

    async def evaluate(self, expression: str, arg: Any = None) -> Any:
        expr = expression.strip()
        if arg is not None:
            call = f"({expr})({json.dumps(arg)})"
        elif _is_js_function(expr):
            call = f"({expr})()"
        else:
            call = expr
        return await self._tab.evaluate(call)

    async def query_selector(self, selector: str) -> Any:
        try:
            return await self._tab.query_selector(selector)
        except Exception:
            return None

    async def content(self) -> str:
        return await self._tab.get_content()

    async def inner_text(self, selector: str) -> str:
        if selector == "body":
            result = await self._tab.evaluate(
                "document.body ? document.body.innerText : ''"
            )
            return str(result or "")
        el = await self.query_selector(selector)
        if el:
            return await el.text_all() if hasattr(el, "text_all") else str(el)
        return ""

    def locator(self, selector: str) -> LocatorAdapter:
        return LocatorAdapter(self, selector)

    def get_by_role(self, role: str, name: re.Pattern[str] | str | None = None) -> LocatorAdapter:
        if isinstance(name, re.Pattern):
            pattern = name.pattern
        elif name:
            pattern = str(name)
        else:
            pattern = ""
        # Map to text search for buttons
        if role == "button" and pattern:
            return LocatorAdapter(self, f'button:has-text("{pattern}")')
        return LocatorAdapter(self, role)

    async def bring_to_front(self) -> None:
        pass

    async def screenshot(self, path: str, full_page: bool = True) -> None:
        try:
            await self._tab.save_screenshot(path, full_page=full_page)
        except Exception as e:
            logger.warning("screenshot_failed", path=path, error=str(e))
            raise
