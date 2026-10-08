from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.scanner import Job, LLMConfig


class JobRejectedError(Exception):
    """The runner can't take this scan as requested; the message is shown to the user."""


class JobRunner(Protocol):
    """Runs queued scans."""

    def on_startup(self) -> None:
        """Called once when the API starts."""

    def is_full(self) -> bool:
        """Whether running + waiting scans have reached max_queued_scans."""

    def check(self, llm: LLMConfig | None) -> None:
        """Raise JobRejectedError when this runner can't run a scan with these options."""

    async def submit(self, job: Job) -> None:
        """Hand a freshly created (pending) scan over to be run."""
