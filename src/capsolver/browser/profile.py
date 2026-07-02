"""Browser profile — load extensions from Chrome Web Store (Brave) or local fallback."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from capsolver.browser.extensions import resolve_discord, resolve_nopecha
from capsolver.browser.nopecha_setup import inject_key, read_nopecha_key
from capsolver.core.config import AppConfig, get_config
from capsolver.core.logging import get_logger

logger = get_logger(__name__)

EXTENSION_IDS = {
    "nopecha": "dknlfmjaanfblgfdfebhijalfmhmjjjo",
    "discord-token-login": "pdmpkpjlmnndlfdllmnekbmgjikhghjg",
}


def _should_load_nopecha(config: AppConfig) -> bool:
    ext_cfg = config.browser.extensions
    if not ext_cfg.load_nopecha:
        return False
    captcha = config.automation.poketwo.captcha
    if captcha.mode == "extension":
        return True
    # Load NopeCHA extension for toolbar visibility + backup; API does primary solving
    return True


async def extensions_to_load(
    config: AppConfig | None = None,
    *,
    include: bool = True,
) -> list[Path]:
    config = config or get_config()

    if not include:
        logger.info("extensions_skipped", reason="disabled_for_session")
        return []

    if config.browser.system_profile_path:
        return []

    paths: dict[str, Path] = {}
    if _should_load_nopecha(config):
        paths["nopecha"] = resolve_nopecha(config)
    paths["discord-token-login"] = resolve_discord(config)

    loaded = [p.resolve() for p in paths.values()]
    logger.info("extensions_resolved", paths=[str(p) for p in loaded])
    return loaded


async def validate_extensions(config: AppConfig | None = None) -> list[Path]:
    return await extensions_to_load(config, include=True)


def extension_ids_for(paths: list[Path]) -> dict[str, str]:
    ids: dict[str, str] = {}
    for path in paths:
        # Store path: .../Extensions/<id>/<version>/
        parent = path.parent.name
        if parent in EXTENSION_IDS:
            ids[parent] = EXTENSION_IDS[parent]
            continue
        name = path.name
        if name in EXTENSION_IDS:
            ids[name] = EXTENSION_IDS[name]
    return ids


async def warmup_profile(
    browser: Any,
    extension_paths: list[Path],
    nopecha_api_key: str = "",
    *,
    configure_nopecha: bool = True,
) -> dict[str, str]:
    """Wait for extensions; inject NopeCHA API key."""
    ids = extension_ids_for(extension_paths)
    if not extension_paths:
        logger.info("profile_warmed", extensions=[])
        return ids

    await asyncio.sleep(2)

    key = read_nopecha_key(nopecha_api_key)
    if configure_nopecha and key and any("nopecha" in str(p) or p.name == "nopecha" for p in extension_paths):
        await inject_key(browser, key)

    logger.info("profile_warmed", extensions=list(ids.keys()), nopecha_key=bool(key))
    return ids
