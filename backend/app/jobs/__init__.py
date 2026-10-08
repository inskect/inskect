from __future__ import annotations

from functools import lru_cache

from app.core import extensions
from app.core.config import Settings, get_settings
from app.jobs.base import JobRejectedError, JobRunner

__all__ = ["JobRejectedError", "JobRunner", "create_runner", "get_runner"]


def create_runner(settings: Settings) -> JobRunner:
    """INSKECT_JOB_RUNNER, by default app.jobs.in_process:InProcessRunner."""
    return extensions.load(settings.job_runner, "INSKECT_JOB_RUNNER")


@lru_cache
def get_runner() -> JobRunner:
    return create_runner(get_settings())
