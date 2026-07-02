#!/usr/bin/env python3
"""Run full Poketwo pipeline test."""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from capsolver.automation.poketwo import PoketwoAutomation
from capsolver.browser.factory import create_launcher
from capsolver.browser.session import BrowserPool
from capsolver.core.config import load_config
from capsolver.jobs.models import Job

URL = os.getenv("POKETWO_VERIFY_URL", "https://verify.poketwo.net/captcha/1519215866414239746")
TOKEN = os.getenv("DISCORD_TOKEN", "").strip()


async def main() -> int:
    os.environ.setdefault("DISPLAY", ":0")
    if not TOKEN:
        print("Set DISCORD_TOKEN in environment before running e2e test.")
        return 1
    config = load_config()
    print(f"engine={config.browser.engine} cf_first={not config.browser.load_extensions_at_startup}")

    job = Job(url=URL, discord_token=TOKEN)
    pool = BrowserPool(create_launcher(config))
    session = await pool.acquire(str(uuid.uuid4())[:8], "e2e")

    async def on_progress(step: str, pct: int, msg: str = "") -> None:
        print(f"[{pct:3d}%] {step}: {msg}")

    ok = False
    try:
        ok = await PoketwoAutomation(config).execute(job, session, on_progress)
        print(f"\nRESULT: {'SUCCESS' if ok else 'FAILED'}")
        for e in job.logs[-20:]:
            print(f"  {e.step}: {e.message}")
        if not ok:
            print("\nBrowser stays open 30s for inspection...")
            await asyncio.sleep(30)
        return 0 if ok else 1
    finally:
        await pool.release(session, cleanup_profile=ok)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
