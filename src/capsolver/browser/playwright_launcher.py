"""Playwright stealth launcher — temp profile, extensions, NopeCHA setup."""

from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, async_playwright

from capsolver.browser.playwright_adapter import PlaywrightPageAdapter
from capsolver.browser.profile import extension_ids_for, extensions_to_load
from capsolver.browser.profile_lock import clean_stale_locks, profile_file_lock
from capsolver.core.config import AppConfig, get_config
from capsolver.core.logging import get_logger
from capsolver.core.platform import PlatformInfo, detect_platform, ensure_display

logger = get_logger(__name__)

BROWSER_BINARIES = ("brave", "brave-browser", "google-chrome-stable", "google-chrome", "chromium")

STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
"""


def find_browser_binary(config: AppConfig) -> str | None:
    if config.browser.executable_path:
        p = Path(config.browser.executable_path)
        if p.exists():
            return str(p)
    for name in BROWSER_BINARIES:
        found = shutil.which(name)
        if found:
            return found
    return None


class BrowserHandle:
    def __init__(
        self,
        playwright: Any,
        context: BrowserContext,
        page: PlaywrightPageAdapter,
        profile_dir: Path,
    ):
        self.playwright = playwright
        self.context = context
        self.browser = context
        self.page = page
        self.profile_dir = profile_dir

    @property
    def pages(self) -> list[PlaywrightPageAdapter]:
        return [self.page]


class PlaywrightLauncher:
    """Puppeteer-stealth style browser via Playwright persistent context."""

    def __init__(self, config: AppConfig | None = None, platform_info: PlatformInfo | None = None):
        self.config = config or get_config()
        self.platform = platform_info or detect_platform()
        self._playwright = None

    async def start(self) -> None:
        if not self.platform.has_display and self.platform.xvfb_available:
            ensure_display(self.platform, self.config.platform.display)
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        logger.info("playwright_ready", platform=self.platform.os_type.value)

    async def stop(self) -> None:
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def release_shared_context(self, session_id: str) -> None:
        pass

    def _profile_dir(self, session_id: str) -> Path:
        cfg = self.config.browser
        if cfg.system_profile_path:
            p = Path(cfg.system_profile_path).expanduser()
            if p.exists():
                return p.resolve()
        if cfg.shared_profile:
            return self.config.resolve_path(cfg.user_data_base) / f"shared_{cfg.shared_profile_id}"
        return self.config.resolve_path(cfg.user_data_base) / "temp" / session_id

    async def create_session(
        self,
        session_id: str | None = None,
        with_extensions: bool | None = None,
    ) -> tuple[BrowserHandle, str, dict[str, str]]:
        await self.start()

        include_ext = (
            with_extensions
            if with_extensions is not None
            else self.config.browser.load_extensions_at_startup
        )
        extension_paths = await extensions_to_load(self.config, include=include_ext)
        sid = session_id or str(uuid.uuid4())
        profile_dir = self._profile_dir(sid)
        profile_dir.mkdir(parents=True, exist_ok=True)
        clean_stale_locks(profile_dir)

        binary = find_browser_binary(self.config)
        args = [
            "--disable-blink-features=AutomationControlled",
        ]
        if extension_paths:
            joined = ",".join(str(p.resolve()) for p in extension_paths)
            args.extend([
                f"--disable-extensions-except={joined}",
                f"--load-extension={joined}",
            ])
        args.extend(self.config.browser.args)

        with profile_file_lock(profile_dir):
            logger.info(
                "launching_playwright_stealth",
                session_id=sid,
                profile=str(profile_dir),
                extensions=[p.name for p in extension_paths],
                binary=binary,
            )
            context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,
                executable_path=binary,
                args=args,
                ignore_default_args=["--enable-automation"],
                viewport={
                    "width": self.config.browser.viewport_width,
                    "height": self.config.browser.viewport_height,
                },
            )

        await context.add_init_script(STEALTH_INIT_SCRIPT)
        page = context.pages[0] if context.pages else await context.new_page()
        adapter = PlaywrightPageAdapter(page, context)

        extension_ids = extension_ids_for(extension_paths)
        captcha = self.config.automation.poketwo.captcha
        if captcha.nopecha_api_key and "nopecha" in extension_ids:
            await self._configure_nopecha(adapter, captcha.nopecha_api_key)

        handle = BrowserHandle(self._playwright, context, adapter, profile_dir)
        logger.info("session_ready", extensions=list(extension_ids.keys()))
        return handle, sid, extension_ids

    async def _configure_nopecha(self, page: PlaywrightPageAdapter, api_key: str) -> None:
        try:
            await page.goto(
                f"https://nopecha.com/setup?api_key={api_key}",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await asyncio.sleep(3)
            logger.info("nopecha_api_key_configured")
        except Exception as e:
            logger.warning("nopecha_setup_failed", error=str(e))

    async def cleanup_session(self, session_id: str) -> None:
        if self.config.browser.system_profile_path or self.config.browser.shared_profile:
            return
        for base in (
            self.config.resolve_path(self.config.browser.user_data_base) / "temp" / session_id,
            self.config.resolve_path(self.config.browser.user_data_base) / session_id,
        ):
            if base.exists():
                shutil.rmtree(base, ignore_errors=True)
                logger.info("temp_profile_deleted", session_id=session_id, path=str(base))
