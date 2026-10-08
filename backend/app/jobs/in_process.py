"""Scans run as asyncio tasks in the API process.

The queue lives in the database, so a restart loses nothing. A scan is `pending` until it starts,
and goes back to `pending` when the API stops mid-scan (scanner.run_job). On startup the runner
picks every pending or running scan back up, oldest first, with its upload and, for AI review, its
credentials: the user's saved key, the server's Claude login, or the one-off key and endpoint held
encrypted for it (scan_secrets, which needs INSKECT_SECRET_KEY). A scan started
MAX_ATTEMPTS times without finishing fails, saying so, rather than running forever.

One API process runs the queue: replicas would each pick up the others' scans.
"""

from __future__ import annotations

import asyncio
import time

from pydantic import ValidationError

from app import claude_key, db, monitoring, scanner, secrets_box, uploads
from app.claude_login import claude_cli_enabled
from app.core.config import get_settings
from app.scanner import Job, JobStatus, LLMConfig

# Starts without finishing before a scan is given up on: the API stopped during each, or the scan
# itself brings the process down.
MAX_ATTEMPTS = 3


class _CantResumeError(Exception):
    """A scan that can't be run again as it was asked for; the message says why."""


class InProcessRunner:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()
        self._semaphore = asyncio.Semaphore(get_settings().max_concurrent_scans)

    def on_startup(self) -> None:
        """Run again the scans a previous process left unfinished, and fail the ones that can't be."""
        resumed: list[Job] = []
        for scan in db.unfinished_scans():
            try:
                resumed.append(_job_for(scan))
            except _CantResumeError as exc:
                _fail(scan, str(exc))
        # Every other upload is one no scan will read any more.
        uploads.clear(keep={job.id for job in resumed})
        for job in resumed:
            db.update_scan(id=job.id, status=JobStatus.PENDING, finished_at=None, result=None, error=None)
            self._start(job)
        if resumed:
            monitoring.log_event("scans_resumed", count=len(resumed))

    def is_full(self) -> bool:
        return len(self._tasks) >= get_settings().max_queued_scans

    def check(self, llm: LLMConfig | None) -> None:
        return None

    async def submit(self, job: Job) -> None:
        if job.llm is not None and not job.llm.use_saved_key and (job.llm.api_key or job.llm.base_url) and secrets_box.is_configured():
            # Kept so the scan can run again after a restart; a saved key is fetched again instead.
            await asyncio.to_thread(claude_key.hold_llm_for_scan, job.id, api_key=job.llm.api_key, base_url=job.llm.base_url)
        self._start(job)

    def _start(self, job: Job) -> None:
        task = asyncio.create_task(self._run(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, job: Job) -> None:
        async with self._semaphore:
            await scanner.run_job(job)
        # Reached only once the scan ran to an end: a cancelled one keeps its credentials.
        db.delete_scan_secret(job.id)


def _fail(scan: dict, error: str) -> None:
    db.update_scan(id=scan["id"], status=JobStatus.ERROR, finished_at=time.time(), result=None, error=error)
    db.delete_scan_secret(scan["id"])
    monitoring.record(monitoring.SCAN_FAILED, error, scan_id=scan["id"], reason="restart")


def _job_for(scan: dict) -> Job:
    if (scan.get("attempts") or 0) >= MAX_ATTEMPTS:
        raise _CantResumeError(f"The scan didn't finish after {MAX_ATTEMPTS} attempts: the API stopped during each one")
    return Job(
        id=scan["id"],
        target=scan["target"],
        llm=_llm_for(scan),
        baseline=scan.get("baseline"),
        use_shipped_baseline=bool(scan.get("use_shipped_baseline")),
        transitive_depth=scan.get("transitive_depth"),
        upload=scan.get("upload"),
        owner_id=scan.get("owner_id"),
        private_source=bool(scan.get("private_source")),
        created_at=scan["created_at"],
    )


def _llm_for(scan: dict) -> LLMConfig | None:
    """The scan's AI settings as it was started: from the credentials held for it, the user's
    saved key, or the server's Claude login."""
    provider, model = scan.get("provider"), scan.get("llm_model")
    if not provider:
        return None
    held = claude_key.held_llm_for_scan(scan["id"]) if secrets_box.is_configured() else None
    if held:
        try:
            return LLMConfig(provider=provider, api_key=held.get("api_key"), base_url=held.get("base_url"), model=model)
        except ValidationError:
            pass
    if provider == "claude_cli":
        if not claude_cli_enabled():
            raise _CantResumeError("The server's Claude login isn't available any more: sign it in again, then scan again")
        return LLMConfig(provider="claude_cli", model=model)
    if provider == "anthropic" and scan.get("owner_id") and claude_key.available():
        saved = claude_key.saved_key(scan["owner_id"])
        if saved:
            return LLMConfig(provider="anthropic", api_key=saved, use_saved_key=True, model=model)
    try:
        # A provider that needs neither key nor endpoint (Ollama on its default address).
        return LLMConfig(provider=provider, model=model)
    except ValidationError:
        raise _CantResumeError(
            "The API restarted, and this scan's AI review key isn't kept across restarts"
            " (set INSKECT_SECRET_KEY to keep it): scan again"
        ) from None
