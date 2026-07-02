"""Stub launcher — real browser runs in Node puppeteer-extra process."""

from __future__ import annotations

import uuid
from pathlib import Path

from capsolver.core.config import AppConfig, get_config
from capsolver.core.logging import get_logger

logger = get_logger(__name__)


class PuppeteerHandle:
    """Placeholder; automation runs in scripts/puppeteer-poketwo.mjs."""

    def __init__(self, profile_dir: Path):
        self.profile_dir = profile_dir
        self.browser = None
        self.context = None
        self.page = None


class PuppeteerLauncher:
    def __init__(self, config: AppConfig | None = None, platform_info=None):
        self.config = config or get_config()

    async def start(self) -> None:
        logger.info("puppeteer_stealth_ready", engine="puppeteer-extra")

    async def stop(self) -> None:
        pass

    async def release_shared_context(self, session_id: str) -> None:
        pass

    async def create_session(
        self, session_id: str | None = None, with_extensions: bool | None = None
    ):
        sid = session_id or str(uuid.uuid4())
        profile_dir = self.config.resolve_path(self.config.browser.user_data_base) / "temp" / sid
        handle = PuppeteerHandle(profile_dir)
        ext_ids = {
            "nopecha": "dknlfmjaanfblgfdfebhijalfmhmjjjo",
            "discord-token-login": "pdmpkpjlmnndlfdllmnekbmgjikhghjg",
        }
        return handle, sid, ext_ids

    async def cleanup_session(self, session_id: str) -> None:
        import shutil

        base = self.config.resolve_path(self.config.browser.user_data_base) / "temp" / session_id
        if base.exists():
            shutil.rmtree(base, ignore_errors=True)
