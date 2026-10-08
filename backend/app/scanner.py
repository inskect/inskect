from __future__ import annotations

import asyncio
import functools
import os
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, model_validator
from skillspector.graph import graph

from app import db, monitoring, repo_connections, scan_logs, uploads
from app.core import extensions
from app.core.config import LLMProvider, Settings, get_settings
from app.scan_runner import run_scan
from app.transitive import transitive_options

TOTAL_GRAPH_STEPS = len([n for n in graph.get_graph().nodes if n not in ("__start__", "__end__")])


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


_NO_API_KEY_PROVIDERS = {"ollama", "claude_cli"}
# Providers that only work with an endpoint of the user's: an Azure resource, or any
# OpenAI-compatible API (Groq, Together, Mistral, a gateway…).
NEEDS_BASE_URL = {"azure_openai", "openai_compatible"}

# The variables skillspector reads each provider's key and endpoint from (skillspector/providers/).
_PROVIDER_ENV_VARS: dict[LLMProvider, tuple[str | None, str | None]] = {
    "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"),
    "openai": ("OPENAI_API_KEY", "OPENAI_BASE_URL"),
    # The model is the Azure deployment's name.
    "azure_openai": ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"),
    "openai_compatible": ("SKILLSPECTOR_COMPAT_API_KEY", "SKILLSPECTOR_COMPAT_BASE_URL"),
    # build.nvidia.com; its endpoint is fixed.
    "nv_build": ("NVIDIA_INFERENCE_KEY", None),
    "ollama": (None, "OLLAMA_BASE_URL"),
    "claude_cli": (None, None),
}


def provider_allowed(provider: LLMProvider, settings: Settings) -> bool:
    """Whether this server lets scans use provider for AI review (INSKECT_AI_PROVIDERS)."""
    if provider == "claude_cli" and not settings.claude_cli:
        return False
    return settings.ai_providers is None or provider in settings.ai_providers


class LLMConfig(BaseModel):
    provider: LLMProvider
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    # Use the Claude key saved to the user's account instead of api_key (app/claude_key.py).
    use_saved_key: bool = False

    @model_validator(mode="after")
    def _require_key_for_remote_providers(self) -> LLMConfig:
        if self.use_saved_key:
            if self.provider != "anthropic":
                raise ValueError("a saved key is only for the anthropic provider")
            return self
        if self.provider not in _NO_API_KEY_PROVIDERS and not (self.api_key and self.api_key.strip()):
            raise ValueError(f"{self.provider} requires an api_key")
        if self.provider in NEEDS_BASE_URL and not (self.base_url and self.base_url.strip()):
            raise ValueError(f"{self.provider} requires a base_url (its endpoint)")
        return self


@dataclass
class Job:
    id: str
    target: str
    llm: LLMConfig | None
    # A baseline file's text (YAML or JSON): findings it accepts are suppressed.
    baseline: str | None = None
    # Apply the baseline the skill ships, if any, when there's no baseline above (the user opted in).
    use_shipped_baseline: bool = False
    # Levels of external references to follow and scan too; None follows none.
    transitive_depth: int | None = None
    # Where an uploaded file is held (app/uploads.py); its name is the target's.
    upload: str | None = None
    # Who started it, and whether it reads a private repository with their connection
    # (app/repo_connections.py): its token is fetched for them when it runs.
    owner_id: str | None = None
    private_source: bool = False
    status: JobStatus = JobStatus.PENDING
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    # Its number among its owner's reports (INS-0001…), once recorded.
    report_no: int | None = None


# skillspector reads provider credentials from os.environ, so AI scans in one process must not overlap.
_llm_lock = asyncio.Lock()


def create_job(
    target: str,
    llm: LLMConfig | None,
    *,
    owner_id: str | None = None,
    baseline: str | None = None,
    use_shipped_baseline: bool = False,
    transitive_depth: int | None = None,
    upload: str | None = None,
    job_id: str | None = None,
    max_active: int | None = None,
    private_source: bool = False,
) -> Job:
    """Record a pending scan; with max_active, only while the owner has fewer in progress (else
    ActiveScansFullError), checked and recorded at once."""
    job = Job(
        id=job_id or uuid.uuid4().hex,
        target=target,
        llm=llm,
        baseline=baseline,
        use_shipped_baseline=use_shipped_baseline,
        transitive_depth=transitive_depth,
        upload=upload,
        owner_id=owner_id,
        private_source=private_source,
    )
    inserted = db.insert_scan(
        id=job.id,
        target=job.target,
        status=job.status,
        created_at=job.created_at,
        provider=llm.provider if llm else None,
        owner_id=owner_id,
        llm_model=llm.model if llm else None,
        baseline=baseline,
        use_shipped_baseline=use_shipped_baseline,
        transitive_depth=transitive_depth,
        upload=upload,
        private_source=private_source,
        max_active=max_active,
    )
    if inserted is None:
        raise ActiveScansFullError(max_active or 0)
    job.report_no = inserted
    return job


class ActiveScansFullError(Exception):
    """The owner already has max_active scans in progress."""

    def __init__(self, limit: int) -> None:
        super().__init__(limit)
        self.limit = limit


def job_from_row(row: db.ScanRow) -> Job:
    """A stored scan as a Job, from its row already read."""
    return Job(
        id=row["id"],
        target=row["target"],
        llm=None,
        status=JobStatus(row["status"]),
        created_at=row["created_at"],
        finished_at=row["finished_at"],
        result=row["result"],
        error=row["error"],
        report_no=row.get("report_no"),
    )


def list_jobs(
    limit: int,
    offset: int,
    *,
    owner_id: str | None = None,
    target: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
) -> tuple[list[db.ScanRow], int]:
    return db.list_scans(limit, offset, owner_id=owner_id, target=target, sort=sort, order=order)


def delete_job(job_id: str) -> bool:
    scan_logs.forget(job_id)
    return db.delete_scan(job_id)


def _mark_running(job: Job) -> None:
    # A scan can be run again (a restart mid-scan); start its log afresh.
    scan_logs.forget(job.id)
    db.update_scan(id=job.id, status=job.status, finished_at=None, result=None, error=None)
    db.start_attempt(job.id)


async def run_job(job: Job) -> None:
    """Run one scan to completion and record the outcome. Every job runner ends up here.

    Never raises for a failed scan: the error is stored on the scan instead. Cancelled (the API is
    stopping), it puts the scan back to pending, its upload kept, to be run again
    (app/jobs/in_process.py), and lets the cancellation through.
    """
    job.status = JobStatus.RUNNING
    # In a thread, like the outcome below: scans share the event loop with requests.
    await asyncio.to_thread(_mark_running, job)
    started = time.time()
    monitoring.log_event("scan_started", scan_id=job.id, ai_review=job.llm is not None)
    try:
        # A private repository's token is its owner's, fetched now: never carried with the scan.
        token = await asyncio.to_thread(repo_connections.require_token, job.owner_id) if job.private_source else None
        job.result = await get_executor().run(job, token=token)
        job.status = JobStatus.DONE
    except asyncio.CancelledError:
        job.status = JobStatus.PENDING
        # Directly, not in a thread: awaiting while cancelled could be cut short, leaving it running.
        scan_logs.flush(job.id)
        db.update_scan(id=job.id, status=job.status, finished_at=None, result=None, error=None)
        monitoring.log_event("scan_interrupted", scan_id=job.id)
        raise
    except Exception as exc:  # noqa: BLE001
        job.error = str(exc)
        job.status = JobStatus.ERROR
    # Never kept once scanned, whatever the outcome.
    await uploads.delete(job.upload)
    job.finished_at = time.time()
    job.llm = None
    # Its last lines first, so the log is whole once the page sees the scan finished.
    await asyncio.to_thread(scan_logs.flush, job.id)
    await asyncio.to_thread(
        db.update_scan,
        id=job.id,
        status=job.status,
        finished_at=job.finished_at,
        result=job.result,
        error=job.error,
    )
    await _report(job, duration=job.finished_at - started)


async def _report(job: Job, *, duration: float) -> None:
    """The scan's outcome for monitoring: a log line, and for a failure a counted event, which may
    send an alert (in a thread: it can wait on a webhook or an SMTP server)."""
    if job.status == JobStatus.DONE:
        verdict = ((job.result or {}).get("risk_assessment") or {}).get("recommendation")
        monitoring.log_event("scan_finished", scan_id=job.id, duration_seconds=round(duration, 1), recommendation=verdict)
        return
    await asyncio.to_thread(monitoring.record, monitoring.SCAN_FAILED, job.error, scan_id=job.id, reason="scan", duration_seconds=round(duration, 1))


class ScanExecutor(Protocol):
    """Where a scan's target is fetched and analysed (INSKECT_SCAN_EXECUTOR)."""

    async def run(self, job: Job, *, token: str | None) -> dict[str, Any]:
        """Scan job's target, or its upload (job.upload, through app/uploads.py), and return
        skillspector's report; raise to fail the scan, with the message to show. token is the
        owner's GitHub token, for a private repository (job.private_source), and None otherwise.
        Report steps and log lines as they come with app/scan_logs.py."""


class LocalExecutor:
    """The default: in this process, in a worker thread."""

    async def run(self, job: Job, *, token: str | None) -> dict[str, Any]:
        if token is not None:
            async with repo_connections.local_copy(job.target, token) as path:
                return await _run_locally(job, path)
        if job.upload is not None:
            async with uploads.local_copy(job.upload, job.target.removeprefix(uploads.TARGET_PREFIX)) as path:
                return await _run_locally(job, path)
        return await _run_locally(job, job.target)


@functools.cache
def get_executor() -> ScanExecutor:
    return extensions.load(get_settings().scan_executor, "INSKECT_SCAN_EXECUTOR")


async def _run_locally(job: Job, path: str) -> dict[str, Any]:
    """Scan path (the target, or a local copy of the upload) in this process."""
    loop = asyncio.get_running_loop()
    scan = functools.partial(
        _invoke_graph,
        job.id,
        path,
        job.llm is not None,
        job.baseline,
        job.transitive_depth,
        label=job.target,
        use_shipped_baseline=job.use_shipped_baseline,
    )
    if job.llm is None:
        return await loop.run_in_executor(None, scan)
    async with _llm_lock:
        with _llm_env(job.llm):
            return await loop.run_in_executor(None, scan)


@contextmanager
def _llm_env(config: LLMConfig) -> Iterator[None]:
    api_key_var, base_url_var = _PROVIDER_ENV_VARS[config.provider]
    keys = {"SKILLSPECTOR_PROVIDER", "SKILLSPECTOR_MODEL", api_key_var, base_url_var} - {None}
    previous = {key: os.environ.get(key) for key in keys}
    try:
        os.environ["SKILLSPECTOR_PROVIDER"] = config.provider
        if config.model:
            os.environ["SKILLSPECTOR_MODEL"] = config.model
        elif "SKILLSPECTOR_MODEL" in os.environ:
            del os.environ["SKILLSPECTOR_MODEL"]
        if api_key_var and config.api_key:
            os.environ[api_key_var] = config.api_key
        if base_url_var:
            if config.base_url:
                os.environ[base_url_var] = config.base_url
            elif base_url_var in os.environ:
                del os.environ[base_url_var]
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _invoke_graph(
    job_id: str,
    target: str,
    use_llm: bool,
    baseline: str | None = None,
    transitive_depth: int | None = None,
    *,
    label: str | None = None,
    use_shipped_baseline: bool = False,
) -> dict[str, Any]:
    """Scan target; label is what the log calls it, when that's not the target (an upload's copy)."""
    scan_logs.start_capture(job_id)
    scan_logs.append(job_id, f"Starting the inspection of {label or target}")
    settings = get_settings()
    baseline_file = None
    try:
        if baseline is not None:
            # skillspector loads baselines from a file.
            baseline_file = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)  # noqa: SIM115
            with baseline_file:
                baseline_file.write(baseline)
        config = {
            "run_name": "inskect-scan",
            "tags": ["inskect"],
            "metadata": {"input_path": target, "use_llm": use_llm},
        }

        def step(node_name: str) -> None:
            scan_logs.append(job_id, f"{node_name} completed")
            scan_logs.increment_progress(job_id)

        try:
            report = run_scan(
                target,
                use_llm=use_llm,
                baseline_path=baseline_file.name if baseline_file else None,
                use_shipped_baseline=use_shipped_baseline,
                on_step=step,
                on_log=lambda line: scan_logs.append(job_id, line),
                config=config,
                # skillspector's own deadline is per scan; a repository of several skills shares it.
                deadline_seconds=settings.max_workflow_seconds,
                transitive=transitive_options(settings, transitive_depth),
                yara_rules_dir=str(settings.yara_rules_dir) if settings.yara_rules_dir else None,
            )
        except Exception as exc:
            scan_logs.append(job_id, f"Inspection failed: {exc}")
            raise
        scan_logs.append(job_id, "Inspection complete")
        return report
    finally:
        scan_logs.stop_capture()
        if baseline_file is not None:
            os.unlink(baseline_file.name)
