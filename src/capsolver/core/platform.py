"""Cross-platform detection and environment setup."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum


class OSType(str, Enum):
    WINDOWS = "windows"
    UBUNTU = "ubuntu"
    DEBIAN = "debian"
    ARCH = "arch"
    LINUX = "linux"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PlatformInfo:
    os_type: OSType
    distro: str
    arch: str
    python_version: str
    has_display: bool
    xvfb_available: bool
    playwright_browsers_path: str | None


def _detect_linux_distro() -> OSType:
    try:
        if os.path.exists("/etc/os-release"):
            with open("/etc/os-release", encoding="utf-8") as f:
                content = f.read().lower()
            if "ubuntu" in content:
                return OSType.UBUNTU
            if "debian" in content:
                return OSType.DEBIAN
            if "arch" in content:
                return OSType.ARCH
    except OSError:
        pass
    return OSType.LINUX


def detect_platform() -> PlatformInfo:
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        os_type = OSType.WINDOWS
        distro = "windows"
    elif system == "linux":
        os_type = _detect_linux_distro()
        distro = os_type.value
    else:
        os_type = OSType.UNKNOWN
        distro = system

    has_display = bool(os.environ.get("DISPLAY")) or system == "windows"
    xvfb_available = shutil.which("Xvfb") is not None

    return PlatformInfo(
        os_type=os_type,
        distro=distro,
        arch=machine,
        python_version=platform.python_version(),
        has_display=has_display,
        xvfb_available=xvfb_available,
        playwright_browsers_path=os.environ.get("PLAYWRIGHT_BROWSERS_PATH"),
    )


def get_system_dependencies(os_type: OSType) -> list[str]:
    """Return package names needed for Playwright on each platform."""
    common = ["libnss3", "libatk-bridge2.0-0", "libdrm2", "libxkbcommon0", "libgbm1"]
    if os_type == OSType.WINDOWS:
        return []
    if os_type in (OSType.UBUNTU, OSType.DEBIAN):
        return common + [
            "libasound2",
            "libatk1.0-0",
            "libcups2",
            "libdbus-1-3",
            "libgtk-3-0",
            "libxcomposite1",
            "libxdamage1",
            "libxfixes3",
            "libxrandr2",
            "xvfb",
            "fonts-liberation",
        ]
    if os_type == OSType.ARCH:
        return [
            "nss",
            "atk",
            "libdrm",
            "libxkbcommon",
            "mesa",
            "alsa-lib",
            "cups",
            "dbus",
            "gtk3",
            "libxcomposite",
            "libxdamage",
            "libxfixes",
            "libxrandr",
            "xorg-server-xvfb",
            "ttf-liberation",
        ]
    return common + ["xvfb"]


def ensure_display(platform_info: PlatformInfo, display: str = ":99") -> None:
    """Set DISPLAY for headless Linux if Xvfb is available."""
    if platform_info.has_display:
        return
    if platform_info.xvfb_available:
        os.environ.setdefault("DISPLAY", display)
        # Check if Xvfb is already running on this display
        try:
            result = subprocess.run(
                ["pgrep", "-f", f"Xvfb {display}"],
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                subprocess.Popen(
                    ["Xvfb", display, "-screen", "0", "1280x720x24", "-ac"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except OSError:
            pass
