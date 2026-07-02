#!/usr/bin/env python3
"""Ensure extensions are installed from Chrome Web Store (via Brave profile)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from capsolver.browser.extensions import resolve_discord, resolve_nopecha
from capsolver.core.config import load_config

NOPECHA_STORE = "https://chromewebstore.google.com/detail/nopecha-captcha-solver/dknlfmjaanfblgfdfebhijalfmhmjjjo"


def main() -> int:
    config = load_config()
    ok = True
    print("Cap-Solver extensions (Chrome Web Store via Brave)\n")

    for name, resolver in (("nopecha", resolve_nopecha), ("discord-token-login", resolve_discord)):
        try:
            path = resolver(config)
            manifest = json.loads((path / "manifest.json").read_text())
            print(f"  ✓ {name}: {manifest.get('name', name)}")
            print(f"      {path}")
        except FileNotFoundError as e:
            print(f"  ✗ {name}: {e}")
            ok = False

    if not ok:
        print(f"\nInstall NopeCHA in Brave from:\n  {NOPECHA_STORE}\n")
        print("Then rerun: python scripts/install-extensions.py")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
