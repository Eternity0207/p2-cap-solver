"""Clean stale Chromium profile locks that cause browser crashes."""

from __future__ import annotations

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path

from capsolver.core.logging import get_logger

logger = get_logger(__name__)

LOCK_FILES = ("SingletonLock", "SingletonSocket", "LOCK", "lockfile")


def clean_stale_locks(profile_dir: Path) -> None:
    """Remove Chromium singleton locks left by crashed browser processes."""
    if not profile_dir.exists():
        return
    for name in LOCK_FILES:
        path = profile_dir / name
        if path.exists():
            try:
                path.unlink()
                logger.info("profile_lock_removed", file=name, profile=str(profile_dir))
            except OSError as e:
                logger.warning("profile_lock_remove_failed", file=name, error=str(e))


@contextmanager
def profile_file_lock(profile_dir: Path):
    """Exclusive file lock so only one browser uses a shared profile at a time."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    lock_path = profile_dir / ".capsolver.lock"
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        clean_stale_locks(profile_dir)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
