"""Browser launcher factory."""

from __future__ import annotations

from capsolver.core.config import AppConfig, get_config


def create_launcher(config: AppConfig | None = None):
    config = config or get_config()
    engine = config.browser.engine.lower()
    if engine in ("puppeteer", "stealth"):
        from capsolver.browser.puppeteer_launcher import PuppeteerLauncher

        return PuppeteerLauncher(config)
    if engine == "playwright":
        from capsolver.browser.playwright_launcher import PlaywrightLauncher

        return PlaywrightLauncher(config)
    from capsolver.browser.launcher import BrowserLauncher

    return BrowserLauncher(config)
