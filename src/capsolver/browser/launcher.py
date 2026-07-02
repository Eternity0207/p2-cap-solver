"""Browser launcher using zendriver (nodriver successor) — undetected, headless=False."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import zendriver as zd
from zendriver.core.config import Config

from capsolver.browser.page_adapter import PageAdapter
from capsolver.browser.profile import extension_ids_for, extensions_to_load, warmup_profile
from capsolver.browser.profile_lock import clean_stale_locks, profile_file_lock
from capsolver.core.config import AppConfig, get_config
from capsolver.core.logging import get_logger
from capsolver.core.platform import PlatformInfo, detect_platform, ensure_display

logger = get_logger(__name__)

BROWSER_BINARIES = ("brave", "brave-browser", "google-chrome-stable", "google-chrome", "chromium")

BLOCKED_BROWSER_ARGS = frozenset({
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--enable-automation",
    "--remote-debugging-port",
})


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


def _extra_browser_args(config: AppConfig) -> list[str]:
    args: list[str] = []
    for arg in config.browser.args:
        base = arg.split("=", 1)[0]
        if base in BLOCKED_BROWSER_ARGS:
            logger.warning("blocked_browser_arg", arg=arg)
            continue
        args.append(arg)
    return args


def _build_zendriver_config(
    config: AppConfig,
    profile_dir: Path,
    extension_paths: list[Path],
    binary: str | None,
) -> Config:
    browser_type = "brave" if binary and "brave" in binary.lower() else "auto"
    zc = Config(
        user_data_dir=str(profile_dir),
        headless=False,
        browser_executable_path=binary,
        browser=browser_type,  # type: ignore[arg-type]
        sandbox=True,
        browser_args=_extra_browser_args(config),
    )
    if extension_paths:
        for path in extension_paths:
            logger.info("extension_registered", path=str(path.resolve()))
        joined = ",".join(str(p.resolve()) for p in extension_paths)
        zc.add_argument(f"--disable-extensions-except={joined}")
        zc.add_argument(f"--load-extension={joined}")
        # Chrome/Brave 127+ ignore --load-extension unless this feature stays disabled.
        # zendriver appends its own --disable-features (without this flag), which would
        # override ours, so this must be the LAST --disable-features on the command line.
        zc.add_argument(
            "--disable-features=IsolateOrigins,site-per-process,"
            "DisableLoadExtensionCommandLineSwitch"
        )
    return zc


class BrowserHandle:
    """Zendriver browser + active tab."""

    def __init__(self, browser: zd.Browser, tab: zd.Tab, page: PageAdapter):
        self.browser = browser
        self.tab = tab
        self.page = page

    @property
    def pages(self) -> list[PageAdapter]:
        return [self.page]


class BrowserLauncher:
    """
    Launch Brave/Chrome via zendriver.

    Extensions load at browser start when load_extensions_at_startup=true.
    """

    def __init__(self, config: AppConfig | None = None, platform_info: PlatformInfo | None = None):
        self.config = config or get_config()
        self.platform = platform_info or detect_platform()

    async def start(self) -> None:
        if not self.platform.has_display and self.platform.xvfb_available:
            ensure_display(self.platform, self.config.platform.display)
        logger.info("zendriver_ready", platform=self.platform.os_type.value)

    async def stop(self) -> None:
        pass

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

    def _should_include_extensions(self, with_extensions: bool | None) -> bool:
        if with_extensions is not None:
            return with_extensions
        return self.config.browser.load_extensions_at_startup

    async def create_session(
        self,
        session_id: str | None = None,
        with_extensions: bool | None = None,
        *,
        configure_nopecha: bool = True,
    ) -> tuple[BrowserHandle, str, dict[str, str]]:
        await self.start()

        include_ext = self._should_include_extensions(with_extensions)
        extension_paths = await extensions_to_load(self.config, include=include_ext)
        sid = session_id or str(uuid.uuid4())
        profile_dir = self._profile_dir(sid)
        profile_dir.mkdir(parents=True, exist_ok=True)
        clean_stale_locks(profile_dir)

        binary = find_browser_binary(self.config)
        zc = _build_zendriver_config(self.config, profile_dir, extension_paths, binary)

        with profile_file_lock(profile_dir):
            logger.info(
                "launching_zendriver",
                session_id=sid,
                profile=str(profile_dir),
                headless=False,
                sandbox=True,
                extensions=[p.name for p in extension_paths],
                binary=binary or zc.browser,
            )
            browser = await zd.Browser.create(zc)

        tab = browser.main_tab
        if tab is None:
            tab = await browser.get("about:blank")
        page = PageAdapter(browser, tab)

        captcha = self.config.automation.poketwo.captcha
        extension_ids = await warmup_profile(
            browser,
            extension_paths,
            nopecha_api_key=captcha.nopecha_api_key,
            configure_nopecha=configure_nopecha and bool(extension_paths),
        )
        if not extension_ids and extension_paths:
            extension_ids = extension_ids_for(extension_paths)

        handle = BrowserHandle(browser, tab, page)
        return handle, sid, extension_ids

    async def cleanup_session(self, session_id: str) -> None:
        if self.config.browser.system_profile_path or self.config.browser.shared_profile:
            return
        for base in (
            self.config.resolve_path(self.config.browser.user_data_base) / "temp" / session_id,
            self.config.resolve_path(self.config.browser.user_data_base) / session_id,
        ):
            if base.exists():
                shutil.rmtree(base, ignore_errors=True)
                logger.info("temp_profile_cleaned", session_id=session_id, path=str(base))
