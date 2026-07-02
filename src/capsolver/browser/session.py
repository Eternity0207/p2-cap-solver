"""Isolated browser session wrapper."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from capsolver.browser.factory import create_launcher
from capsolver.browser.launcher import BrowserHandle, BrowserLauncher
from capsolver.browser.page_adapter import PageAdapter
from capsolver.browser.profile_lock import clean_stale_locks
from capsolver.core.config import get_config
from capsolver.core.logging import get_logger

logger = get_logger(__name__)


def _cookies_to_params(cookies: list[Any]) -> list[Any]:
    """Convert CDP Cookie objects to CookieParam for restore after browser restart."""
    from zendriver import cdp

    params: list[Any] = []
    for c in cookies:
        params.append(
            cdp.network.CookieParam(
                name=c.name,
                value=c.value,
                domain=c.domain,
                path=c.path or "/",
                secure=bool(c.secure),
                http_only=bool(getattr(c, "http_only", False)),
            )
        )
    return params


class BrowserSession:
    """Manages a single isolated browser session lifecycle."""

    def __init__(
        self,
        launcher: BrowserLauncher,
        session_id: str,
        handle: BrowserHandle,
        extension_ids: dict[str, str],
        artifacts_dir: Path,
    ):
        self.launcher = launcher
        self.session_id = session_id
        self.handle = handle
        self.context = handle  # backward compat alias
        self.extension_ids = extension_ids
        self.artifacts_dir = artifacts_dir
        self.created_at = datetime.now(timezone.utc)
        self._closed = False
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    async def page(self) -> PageAdapter:
        return await self.get_or_create_page()

    async def get_or_create_page(self) -> PageAdapter:
        return self.handle.page

    async def reload_with_extensions(self, preserve_url: str | None = None) -> PageAdapter:
        """Stop browser and relaunch on same profile with NopeCHA + Discord extensions."""
        cfg = self.launcher.config.browser
        if not cfg.load_extensions_after_cloudflare and not cfg.load_extensions_at_startup:
            logger.info("reload_with_extensions_skipped", reason="disabled_in_config")
            return self.handle.page

        url = preserve_url or self.handle.page.url
        profile_dir = self.launcher._profile_dir(self.session_id)
        logger.info(
            "reload_with_extensions",
            session_id=self.session_id,
            url=url,
            profile=str(profile_dir),
        )

        saved_cookies: list[Any] = []
        try:
            saved_cookies = list(await self.handle.browser.cookies.get_all())
            logger.info("cookies_saved_before_reload", count=len(saved_cookies))
        except Exception as e:
            logger.warning("cookie_save_before_reload_failed", error=str(e))

        try:
            await self.handle.browser.stop()
        except Exception as e:
            logger.warning("browser_stop_before_reload", error=str(e))

        clean_stale_locks(profile_dir)
        await asyncio.sleep(3)

        handle, _, ext_ids = await self.launcher.create_session(
            session_id=self.session_id,
            with_extensions=True,
            configure_nopecha=True,
        )
        self.handle = handle
        self.extension_ids = ext_ids

        if not ext_ids:
            logger.error("extensions_not_loaded_after_reload")
            raise RuntimeError("Extensions failed to load after Cloudflare")

        logger.info("extensions_loaded", names=list(ext_ids.keys()))

        if saved_cookies:
            try:
                await handle.browser.cookies.set_all(_cookies_to_params(saved_cookies))
                logger.info("cookies_restored_after_reload", count=len(saved_cookies))
            except Exception as e:
                logger.warning("cookie_restore_after_reload_failed", error=str(e))

        page = handle.page

        if url and url not in ("about:blank", "", "chrome://extensions"):
            await page.goto(url, wait_until="domcontentloaded", timeout=120000)
            await asyncio.sleep(4)

        return page

    async def screenshot(self, name: str) -> str:
        path = self.artifacts_dir / f"{name}.png"
        try:
            await self.handle.page.screenshot(str(path), full_page=True)
            logger.info("screenshot_captured", session_id=self.session_id, path=str(path))
        except Exception as e:
            logger.warning("screenshot_skipped", session_id=self.session_id, error=str(e))
        return str(path)

    async def close(self, cleanup_profile: bool = True) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if hasattr(self.handle, "context") and hasattr(self.handle.context, "close"):
                await self.handle.context.close()
            elif hasattr(self.handle.browser, "stop"):
                await self.handle.browser.stop()
        except Exception as e:
            logger.warning("browser_stop_error", session_id=self.session_id, error=str(e))
        if cleanup_profile:
            await self.launcher.cleanup_session(self.session_id)
        logger.info(
            "session_closed",
            session_id=self.session_id,
            engine=get_config().browser.engine,
        )


class BrowserPool:
    """Semaphore-limited pool for concurrent browser sessions."""

    def __init__(self, launcher: BrowserLauncher | None = None):
        self.config = get_config()
        self.launcher = launcher or create_launcher(self.config)
        self._semaphore = asyncio.Semaphore(self.config.browser.max_concurrent)
        self._active: dict[str, BrowserSession] = {}
        self._lock = asyncio.Lock()

    @property
    def max_concurrent(self) -> int:
        return self.config.browser.max_concurrent

    @property
    def active_count(self) -> int:
        return len(self._active)

    async def acquire(self, job_id: str, artifacts_subdir: str) -> BrowserSession:
        await self._semaphore.acquire()
        try:
            artifacts_dir = self.config.resolve_path(self.config.jobs.artifacts_dir) / artifacts_subdir
            handle, session_id, ext_ids = await self.launcher.create_session(
                session_id=f"{job_id}_{session_id_suffix()}",
                with_extensions=self.config.browser.load_extensions_at_startup,
            )
            session = BrowserSession(
                launcher=self.launcher,
                session_id=session_id,
                handle=handle,
                extension_ids=ext_ids,
                artifacts_dir=artifacts_dir,
            )
            async with self._lock:
                self._active[session_id] = session
            logger.info("session_acquired", job_id=job_id, session_id=session_id, active=self.active_count)
            return session
        except Exception:
            self._semaphore.release()
            raise

    async def release(self, session: BrowserSession, cleanup_profile: bool = True) -> None:
        session_id = session.session_id
        await session.close(cleanup_profile=cleanup_profile)
        async with self._lock:
            self._active.pop(session_id, None)
        self._semaphore.release()
        logger.info("session_released", session_id=session_id, active=self.active_count)

    async def shutdown(self) -> None:
        async with self._lock:
            sessions = list(self._active.values())
        for session in sessions:
            await self.release(session)
        await self.launcher.stop()


def session_id_suffix() -> str:
    import uuid
    return uuid.uuid4().hex[:8]
