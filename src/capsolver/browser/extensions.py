"""Fetch extensions fresh from the Chrome Web Store on every run.

No local extension folders are kept. Each call downloads the CRX for the given
extension ID, unpacks it into ``data/ext_cache/<name>/``, and returns that path.
If the download fails, we fall back to a copy already installed in Brave/Chrome.
"""

from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path

import httpx

from capsolver.core.config import AppConfig, get_config
from capsolver.core.logging import get_logger

logger = get_logger(__name__)

NOPECHA_ID = "dknlfmjaanfblgfdfebhijalfmhmjjjo"
DISCORD_ID = "pdmpkpjlmnndlfdllmnekbmgjikhghjg"

_CRX_URL = (
    "https://clients2.google.com/service/update2/crx"
    "?response=redirect&acceptformat=crx2,crx3&prodversion=131.0"
    "&x=id%3D{ext_id}%26installsource%3Dondemand%26uc"
)

_BRAVE_EXT_ROOTS = (
    Path.home() / ".config/BraveSoftware/Brave-Browser/Default/Extensions",
    Path.home() / ".config/google-chrome/Default/Extensions",
    Path.home() / ".config/chromium/Default/Extensions",
)


def _cache_dir(config: AppConfig, name: str) -> Path:
    return config.resolve_path(config.browser.user_data_base).parent / "ext_cache" / name


def _download_crx(ext_id: str, dest: Path) -> bool:
    url = _CRX_URL.format(ext_id=ext_id)
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=120)
        resp.raise_for_status()
    except Exception as e:
        logger.warning("crx_download_failed", id=ext_id, error=str(e))
        return False

    data = resp.content
    start = data.find(b"PK\x03\x04")
    if start < 0:
        logger.warning("crx_not_a_zip", id=ext_id)
        return False

    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(io.BytesIO(data[start:])) as zf:
            zf.extractall(dest)
    except Exception as e:
        logger.warning("crx_extract_failed", id=ext_id, error=str(e))
        return False

    # Chrome refuses to load unpacked extensions containing a _metadata dir.
    meta = dest / "_metadata"
    if meta.exists():
        shutil.rmtree(meta, ignore_errors=True)

    if not (dest / "manifest.json").exists():
        logger.warning("crx_no_manifest", id=ext_id)
        return False

    logger.info("crx_downloaded", id=ext_id, path=str(dest))
    return True


def _copy_from_browser(ext_id: str, dest: Path) -> bool:
    for root in _BRAVE_EXT_ROOTS:
        base = root / ext_id
        if not base.is_dir():
            continue
        versions = [p for p in base.iterdir() if p.is_dir() and (p / "manifest.json").exists()]
        if not versions:
            continue
        src = max(versions, key=lambda p: p.stat().st_mtime)
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(src, dest)
        logger.info("extension_copied_from_browser", id=ext_id, src=str(src), dest=str(dest))
        return True
    return False


def _resolve(ext_id: str, name: str, config: AppConfig) -> Path:
    dest = _cache_dir(config, name)
    if _download_crx(ext_id, dest):
        return dest
    logger.info("crx_fallback_to_browser", id=ext_id)
    if _copy_from_browser(ext_id, dest):
        return dest
    raise FileNotFoundError(
        f"Could not fetch {name} ({ext_id}) from the Chrome Web Store or a local browser. "
        "Check your internet connection or install it once in Brave."
    )


def resolve_nopecha(config: AppConfig | None = None) -> Path:
    return _resolve(NOPECHA_ID, "nopecha", config or get_config())


def resolve_discord(config: AppConfig | None = None) -> Path:
    return _resolve(DISCORD_ID, "discord-token-login", config or get_config())
