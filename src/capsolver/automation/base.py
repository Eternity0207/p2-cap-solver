"""Base automation executor."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable, Awaitable

if TYPE_CHECKING:
    from capsolver.browser.session import BrowserSession
    from capsolver.jobs.models import Job


class AutomationExecutor(ABC):
    @abstractmethod
    async def execute(
        self,
        job: "Job",
        session: "BrowserSession",
        on_progress: Callable[[str, int, str], Awaitable[None]] | None = None,
    ) -> bool:
        """Run automation. Returns True on success."""
        ...
