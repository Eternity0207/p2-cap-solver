#!/usr/bin/env python3
"""Verify extensions load at browser startup."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from capsolver.browser.launcher import BrowserLauncher
from capsolver.core.config import load_config


async def main() -> int:
    if not os.environ.get("DISPLAY"):
        os.environ["DISPLAY"] = ":0"

    config = load_config()
    print(f"load_extensions_at_startup: {config.browser.load_extensions_at_startup}")
    print(f"NopeCHA API key set: {bool(config.automation.poketwo.captcha.nopecha_api_key)}")

    launcher = BrowserLauncher(config)
    handle, sid, ext_ids = await launcher.create_session()
    print(f"Session: {sid}")
    print(f"Extensions: {ext_ids}")

    await handle.page.goto("https://example.com", wait_until="domcontentloaded", timeout=60000)
    await asyncio.sleep(2)
    from capsolver.browser.session import BrowserSession

    artifacts = ROOT / "data/artifacts" / "ext_test"
    session = BrowserSession(launcher, sid, handle, ext_ids, artifacts)
    path = await session.screenshot("startup_extensions")
    print(f"Screenshot: {path}")
    await session.close()
    return 0 if ext_ids else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
