#!/usr/bin/env python3
"""
Cloudflare diagnostic — compare clean vs extension vs production launch.

Checks (per troubleshooting guide):
  1. Console errors / CSP violations
  2. Failed network requests (403, blocked scripts)
  3. Launch flags (--no-sandbox, remote-debugging)
  4. User-Agent
  5. Extension interference
  6. cf_clearance cookie timing
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Project root on path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from patchright.async_api import async_playwright

from capsolver.browser.diagnostics import attach_listeners, collect_snapshot, save_report

URL = "https://verify.poketwo.net/captcha/1519215866414239746"
DISCORD_EXT = str(ROOT / "extensions/discord-token-login")
BASE_PROFILE = ROOT / "data/browser_profiles/cf_diag"


def launch_kwargs_clean(profile: Path) -> dict:
    return {
        "executable_path": "/usr/bin/brave",
        "headless": False,
        "no_viewport": True,
        "chromium_sandbox": True,
        "args": [],
        "ignore_default_args": ["--enable-automation", "--no-sandbox", "--disable-setuid-sandbox"],
    }


def launch_kwargs_discord_ext(profile: Path) -> dict:
    kw = launch_kwargs_clean(profile)
    kw["args"] = [
        f"--disable-extensions-except={DISCORD_EXT}",
        f"--load-extension={DISCORD_EXT}",
    ]
    return kw


async def run_scenario(name: str, profile_suffix: str, kwargs: dict, wait_seconds: int = 90) -> dict:
    profile = BASE_PROFILE / profile_suffix
    profile.mkdir(parents=True, exist_ok=True)
    print(f"\n{'='*60}\nSCENARIO: {name}\nProfile: {profile}\n{'='*60}")

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(str(profile), **kwargs)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        diag = await collect_snapshot(page, ctx, kwargs.get("args", []))
        attach_listeners(page, diag)

        print("Navigating...")
        await page.goto(URL, wait_until="domcontentloaded", timeout=120000)

        timeline = []
        for i in range(wait_seconds // 2):
            await asyncio.sleep(2)
            cookies = await ctx.cookies("https://verify.poketwo.net")
            cf = any(c.get("name") == "cf_clearance" for c in cookies)
            try:
                text = (await page.inner_text("body")).lower()[:100].replace("\n", " ")
            except Exception:
                text = "?"
            verify = await page.locator('button:has-text("Verify")').count()
            entry = {"t": i * 2, "cf_clearance": cf, "verify_btn": verify > 0, "body": text}
            timeline.append(entry)
            print(f"  [{i*2:3d}s] cf={cf} verify={verify} | {text}")
            if verify > 0 or (cf and "verifying you are human" not in text and "performing security" not in text):
                break

        diag = await collect_snapshot(page, ctx, kwargs.get("args", []))
        diag.extension_count = len(kwargs.get("args", [])) // 2  # rough: load-extension pairs

        report_path = ROOT / "data" / "diagnostics" / f"{profile_suffix}.json"
        save_report(diag, report_path)

        await page.screenshot(path=str(ROOT / "data" / "diagnostics" / f"{profile_suffix}.png"), full_page=True)
        await ctx.close()

        result = {
            "scenario": name,
            "report": str(report_path),
            "issues": diag.issues(),
            "timeline_tail": timeline[-5:],
            "passed": any(e.get("verify_btn") for e in timeline) or (
                any(e.get("cf_clearance") for e in timeline)
                and not any("verifying you are human" in e.get("body", "") for e in timeline[-3:])
            ),
        }
        print(f"Issues: {json.dumps(diag.issues(), indent=2)}")
        return result


async def main():
    parser = argparse.ArgumentParser(description="Diagnose Cloudflare verification failures")
    parser.add_argument("--wait", type=int, default=60, help="Seconds to observe each scenario")
    parser.add_argument("--scenario", choices=["all", "clean", "discord-ext", "production"], default="clean")
    args = parser.parse_args()

    scenarios = []
    if args.scenario in ("all", "clean"):
        scenarios.append(("clean_no_extensions", "clean", launch_kwargs_clean(BASE_PROFILE / "clean")))
    if args.scenario in ("all", "discord-ext"):
        scenarios.append(("discord_extension_only", "discord_ext", launch_kwargs_discord_ext(BASE_PROFILE / "discord_ext")))
    if args.scenario in ("all", "production"):
        from capsolver.browser.launcher import BrowserLauncher
        from capsolver.core.config import load_config

        config = load_config(str(ROOT / "config/default.yaml"), str(ROOT / "config/local.yaml"))
        launcher = BrowserLauncher(config)
        # We'll document production args separately
        ext_paths = await __import__("capsolver.browser.profile", fromlist=["extensions_to_load"]).extensions_to_load(config)
        from capsolver.browser.launcher import _safe_browser_args

        prod_args = _safe_browser_args(config, ext_paths)
        scenarios.append(("production_config", "production", {
            **launch_kwargs_clean(BASE_PROFILE / "production"),
            "args": prod_args,
        }))

    results = []
    for name, suffix, kw in scenarios:
        try:
            results.append(await run_scenario(name, suffix, kw, args.wait))
        except Exception as e:
            results.append({"scenario": name, "error": str(e), "passed": False})
            print(f"ERROR in {name}: {e}")

    summary_path = ROOT / "data" / "diagnostics" / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(f"\n{'='*60}\nSUMMARY\n{'='*60}")
    for r in results:
        status = "PASS" if r.get("passed") else "FAIL"
        print(f"  [{status}] {r.get('scenario')}: {r.get('issues', r.get('error', []))}")
    print(f"\nFull reports: {ROOT / 'data' / 'diagnostics'}/")


if __name__ == "__main__":
    asyncio.run(main())
