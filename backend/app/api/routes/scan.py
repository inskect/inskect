import asyncio
import json
import os
import tempfile
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel, Field, ValidationError, field_validator
from skillspector.suppression import dump_baseline

from app import (
    claude_key,
    db,
    exports,
    monitoring,
    quotas,
    rate_limit,
    repo_connections,
    rescan,
    secrets_box,
    sharing,
    uploads,
)
from app.ai_review import AIReview, ai_review_status
from app.ai_usage import TokenTotals, token_totals
from app.auth import Viewer, audit
from app.auth.deps import CurrentViewer, ScanViewer
from app.claude_login import claude_cli_enabled
from app.core.config import get_settings
from app.jobs import JobRejectedError, get_runner
from app.scan_logs import get_logs_after, get_progress, listed_progress
from app.scan_runner import MAX_BASELINE_BYTES, baseline_state, is_mcp_entry
from app.scanner import (
    TOTAL_GRAPH_STEPS,
    ActiveScansFullError,
    Job,
    JobStatus,
    LLMConfig,
    create_job,
    delete_job,
    job_from_row,
    list_jobs,
    provider_allowed,
)
from app.targets import mcp_entry_url, raw_file_url

router = APIRouter(prefix="/scan", tags=["scan"])


def _rate_limit_scan(request: Request, viewer: ScanViewer) -> None:
    """Per signed-in user (per address without accounts), plus a cap per address shared by every
    account signed in from it, so opening more accounts doesn't buy more scans."""
    settings = get_settings()
    window = settings.scan_rate_limit_window_seconds
    subject = rate_limit.subject_key(request, viewer)
    rate_limit.enforce(f"scan:{subject}", settings.scan_rate_limit, window, "You've started a lot of inspections")
    if viewer.user_id:
        address = rate_limit.client_key(request)
        rate_limit.enforce(f"scan:ip:{address}", settings.scan_ip_rate_limit, window, "Too many scans from this address")


def check_baseline(text: str) -> None:
    """Refuse a baseline skillspector wouldn't load, with its reason, before the scan is queued."""
    if len(text.encode()) > MAX_BASELINE_BYTES:
        raise HTTPException(status_code=422, detail=f"The baseline file is larger than {MAX_BASELINE_BYTES // 1024} KB")
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as file:
        file.write(text)
    try:
        baseline_state(file.name)
    except ValueError as exc:
        # skillspector's messages name the file: here, a temporary one.
        reason = str(exc).replace(f": {file.name}", "").replace(file.name, "the file")
        raise HTTPException(status_code=422, detail=f"Couldn't use the baseline file: {reason}") from exc
    finally:
        os.unlink(file.name)


class ScanOptions(BaseModel):
    llm: LLMConfig | None = None
    # A skillspector baseline file's text (YAML or JSON): the findings it accepts are suppressed.
    # Its size is checked by check_baseline, for a readable error.
    baseline: str | None = None
    # Apply the baseline the skill ships (.skillspector-baseline.yaml at its top), if any. Its author
    # wrote it, so it's off unless the user opts in.
    use_shipped_baseline: bool = False
    # Follow the skill's external references this many levels deep (skillspector's --transitive).
    transitive_depth: int | None = Field(default=None, ge=1)


class ScanRequest(ScanOptions):
    # A link, or an MCP server's name. Uploads go to POST /scan/upload.
    target: str

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("target is required")
        if entry := mcp_entry_url(value):
            return entry
        if not value.startswith(get_settings().allowed_target_schemes):
            allowed = " or ".join(get_settings().allowed_target_schemes)
            raise ValueError(f"target must start with {allowed} (a Git repo, zip, or file URL), or name an MCP server")
        # Stored rewritten too, so the history shows what was actually scanned.
        return raw_file_url(value)


class ScanQueuedResponse(BaseModel):
    id: str
    status: JobStatus


class AITokens(BaseModel):
    """Tokens a scan's AI review used; None for counters the provider didn't report."""

    input: int | None
    output: int | None
    cached: int | None


def _ai_tokens(totals: TokenTotals) -> AITokens | None:
    return AITokens(**totals._asdict()) if any(value is not None for value in totals) else None


class ScanStatusResponse(BaseModel):
    id: str
    # Its number among its owner's reports, shown as INS-0001: a label, the id stays the reference.
    report_no: int | None = None
    target: str
    status: JobStatus
    created_at: float
    finished_at: float | None
    result: dict | None
    error: str | None
    ai_review: AIReview | None
    ai_tokens: AITokens | None
    completed_steps: int
    total_steps: int
    # Whether POST /scan/{id}/rescan can scan the target again as this scan did.
    rescan: bool = False
    # What changed since the target's previous scan (app/rescan.py): None for its first, or one
    # not finished. Each finding in result is then marked `change`: new or unchanged.
    comparison: dict | None = None
    # Whether the result is shared at a read-only link (app/sharing.py), and that link's token
    # (/shared/{token}) when it can be shown again: kept encrypted, with SECRET_KEY.
    shared: bool = False
    share_token: str | None = None
    # Whether the shared result is on its target's status badge (app/api/routes/badge.py).
    badge: bool = False
    # Whether it read a private repository with its owner's connection (app/repo_connections.py).
    private_source: bool = False


class ScanSummaryResponse(BaseModel):
    id: str
    report_no: int | None = None
    target: str
    status: JobStatus
    created_at: float
    finished_at: float | None
    error: str | None
    risk_score: float | None
    severity: str | None
    recommendation: str | None
    ai_review: AIReview | None
    completed_steps: int
    total_steps: int
    rescan: bool = False


class ScanHistoryResponse(BaseModel):
    items: list[ScanSummaryResponse]
    total: int


class ScanLogsResponse(BaseModel):
    lines: list[str]
    # Pass it back as ?after= to get only the lines logged since.
    cursor: int


# The name skillspector looks for in a skill, and writes by default.
SHIPPED_NAME = ".skillspector-baseline.yaml"


class BaselineResponse(BaseModel):
    filename: str
    content: str


def _skill_summary(entry: dict) -> dict:
    """A skill of a multi-skill scan without its report, which GET /scan/{id}/skills/{index} serves."""
    report = entry.get("report")
    if report is None:
        return {"path": entry["path"], "name": entry["name"], "error": entry.get("error")}
    return {
        "path": entry["path"],
        "name": entry["name"],
        "risk_assessment": report.get("risk_assessment"),
        "issue_count": len(report.get("issues") or []),
        "suppressed_count": report.get("suppressed_count", 0),
        "execution_successful": report.get("execution_successful", True),
        "ai_review": ai_review_status(report),
    }


def _without_skill_reports(result: dict | None) -> dict | None:
    # Each skill's report can be large; together they could pass a function's response size limit.
    if not result or "skills" not in result:
        return result
    return {**result, "skills": [_skill_summary(entry) for entry in result["skills"]]}


def _to_response(job: Job) -> ScanStatusResponse:
    completed_steps = TOTAL_GRAPH_STEPS if job.status == JobStatus.DONE else get_progress(job.id)
    return ScanStatusResponse(
        id=job.id,
        report_no=job.report_no,
        target=job.target,
        status=job.status,
        created_at=job.created_at,
        finished_at=job.finished_at,
        result=_without_skill_reports(job.result),
        error=job.error,
        ai_review=ai_review_status(job.result),
        ai_tokens=_ai_tokens(token_totals(job.result)),
        completed_steps=completed_steps,
        total_steps=TOTAL_GRAPH_STEPS,
    )


def _resolve_llm(llm: LLMConfig | None, viewer: Viewer) -> LLMConfig | None:
    """Apply this server's provider rules and swap in the user's saved Claude key when asked for."""
    if llm is None:
        return None
    settings = get_settings()
    if not provider_allowed(llm.provider, settings):
        raise HTTPException(status_code=422, detail="That AI provider isn't available for AI review on this server")
    if llm.base_url and not settings.allow_custom_ai_url:
        # It would have this server make requests to an address of the scan's choosing.
        raise HTTPException(status_code=422, detail="A custom base URL isn't allowed on this server")
    if not llm.use_saved_key:
        return llm
    key = claude_key.saved_key(viewer.user_id) if viewer.user_id and claude_key.available() else None
    if key is None:
        raise HTTPException(status_code=400, detail="Connect your Claude key on your account page first, or paste a key for this inspection")
    # Held in memory for this scan only; the queue runner never stores a saved key again.
    return llm.model_copy(update={"api_key": key})


@router.post("", response_model=ScanQueuedResponse, dependencies=[Depends(_rate_limit_scan)])
async def start_scan(req: ScanRequest, viewer: ScanViewer) -> ScanQueuedResponse:
    return await queue_scan(req.target, req, viewer)


@router.post("/upload", response_model=ScanQueuedResponse, dependencies=[Depends(_rate_limit_scan)])
async def start_upload_scan(
    viewer: ScanViewer,
    file: Annotated[UploadFile, File()],
    # The scan's options (ScanOptions), as JSON: a form can't nest them.
    options: Annotated[str, Form()] = "{}",
) -> ScanQueuedResponse:
    """Scan a .zip of a skill, or a SKILL.md, sent with the request."""
    try:
        parsed = ScanOptions.model_validate(json.loads(options))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail="The inspection options aren't valid") from exc
    try:
        name = uploads.safe_name(file.filename or "")
        data = await file.read(uploads.max_bytes() + 1)
        uploads.check_content(name, data)
    except uploads.UploadRejectedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    async def keep(scan_id: str) -> str:
        return await asyncio.to_thread(uploads.save, scan_id, name, data)

    return await queue_scan(uploads.target_for(name), parsed, viewer, keep_upload=keep)


async def queue_scan(
    target: str,
    req: ScanOptions,
    viewer: Viewer,
    *,
    keep_upload: Callable[[str], Awaitable[str]] | None = None,
) -> ScanQueuedResponse:
    """Check a scan may start, and queue it: every route that starts a scan ends here, and so can
    one an extension adds (docs/EXTENDING.md). keep_upload stores an upload for the scan, once
    everything else allows it, and returns where it's held; it raises UploadRejectedError for a
    file that can't be scanned. The database and GitHub calls run in threads, off the event loop."""
    llm, limits, private_source = await asyncio.to_thread(_admit_scan, target, req, viewer, upload=keep_upload is not None)
    job_id = uuid.uuid4().hex
    upload = None
    if keep_upload is not None:
        try:
            upload = await keep_upload(job_id)
        except uploads.UploadRejectedError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        job = await asyncio.to_thread(
            _record_scan, target, req, viewer, llm, limits, job_id=job_id, upload=upload, private_source=private_source
        )
    except BaseException:
        await uploads.delete(upload)
        raise
    try:
        await get_runner().submit(job)
    except Exception as exc:
        # Don't leave a scan pending forever if it never reached the queue.
        await asyncio.to_thread(
            db.update_scan, id=job.id, status=JobStatus.ERROR, finished_at=time.time(), result=None, error="Couldn't queue the inspection"
        )
        await uploads.delete(upload)
        await asyncio.to_thread(monitoring.record, monitoring.SCAN_FAILED, f"Couldn't queue the scan: {exc}", scan_id=job.id, reason="queue")
        raise HTTPException(status_code=503, detail="Couldn't queue the inspection — try again in a moment") from exc
    return ScanQueuedResponse(id=job.id, status=job.status)


def _admit_scan(
    target: str, req: ScanOptions, viewer: Viewer, *, upload: bool
) -> tuple[LLMConfig | None, quotas.ScanLimits, bool]:
    """Whether the scan may start, before anything is stored: its AI review, the viewer's limits,
    and whether it reads a private repository."""
    limits = quotas.current(viewer.user)
    quotas.ensure_not_paused(limits)
    if is_mcp_entry(target) and (req.llm or req.baseline is not None or req.use_shipped_baseline or req.transitive_depth):
        # Its checks read the registry entry alone: there's no code to review, suppress or follow.
        raise HTTPException(
            status_code=422,
            detail="An MCP server inspection checks its registry entry only: AI review, baselines and external references don't apply",
        )
    if req.baseline is not None and req.use_shipped_baseline:
        raise HTTPException(status_code=422, detail="Use either your baseline file or the one the skill ships, not both")
    if req.baseline is not None:
        check_baseline(req.baseline)
    max_depth = get_settings().transitive_max_depth
    if req.transitive_depth is not None and req.transitive_depth > max_depth:
        detail = (
            "Following external references is turned off on this server"
            if max_depth == 0
            else f"External references can be followed at most {max_depth} level{'s' if max_depth != 1 else ''} deep on this server"
        )
        raise HTTPException(status_code=422, detail=detail)
    llm = _resolve_llm(req.llm, viewer)
    private_source = False
    if not upload and not is_mcp_entry(target):
        # A private GitHub repository the user's connection reads: scanned with their token.
        try:
            private_source = repo_connections.private_for(viewer.user_id, target)
        except repo_connections.NoAccessError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    runner = get_runner()
    try:
        runner.check(llm)
    except JobRejectedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if runner.is_full():
        raise HTTPException(status_code=503, detail="The inspection queue is full — try again in a few minutes")
    return llm, limits, private_source


def _record_scan(
    target: str,
    req: ScanOptions,
    viewer: Viewer,
    llm: LLMConfig | None,
    limits: quotas.ScanLimits,
    *,
    job_id: str,
    upload: str | None,
    private_source: bool,
) -> Job:
    """Store the pending scan, and count it towards the viewer's quotas."""
    # Recorded only while the user has room for one more in progress: the check and the insert
    # are one step, so simultaneous requests can't overshoot.
    try:
        job = create_job(
            target,
            llm,
            owner_id=viewer.user_id,
            baseline=req.baseline,
            use_shipped_baseline=req.use_shipped_baseline,
            transitive_depth=req.transitive_depth,
            upload=upload,
            job_id=job_id,
            max_active=quotas.active_limit(viewer, limits),
            private_source=private_source,
        )
    except ActiveScansFullError as exc:
        quotas.refuse_active(exc.limit)
    # Last, so a scan refused for any other reason doesn't count towards today's quota.
    try:
        quotas.count_today(viewer, limits)
    except BaseException:
        db.delete_scan(job.id)
        raise
    return job


class _Rescans:
    """Which scans a viewer can rescan as they ran: not an upload, whose file is gone, and AI review
    only when it needs no key pasted again (the server's Claude login, or the viewer's saved key)."""

    def __init__(self, viewer: Viewer) -> None:
        self._viewer = viewer
        self._saved_key: bool | None = None

    def _has_saved_key(self) -> bool:
        if self._saved_key is None:
            user_id = self._viewer.user_id
            self._saved_key = bool(user_id and claude_key.available() and claude_key.saved_key(user_id))
        return self._saved_key

    def llm(self, scan: dict) -> LLMConfig | None:
        """The AI settings to rescan with; raises ValueError when they'd need a key again."""
        provider = scan.get("provider")
        if provider is None:
            return None
        if provider == "claude_cli" and claude_cli_enabled():
            return LLMConfig(provider="claude_cli", model=scan.get("llm_model"))
        if provider == "anthropic" and self._has_saved_key():
            return LLMConfig(provider="anthropic", use_saved_key=True, model=scan.get("llm_model"))
        raise ValueError("This inspection's AI review needs its key again: use Inspect again, and give it")

    def allowed(self, scan: dict) -> bool:
        if scan["status"] not in (JobStatus.DONE, JobStatus.ERROR) or uploads.is_upload_target(scan["target"]):
            return False
        try:
            self.llm(scan)
        except ValueError:
            return False
        return True


@router.get("", response_model=ScanHistoryResponse)
def read_scan_history(
    viewer: ScanViewer,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    # Only this target's scans: its timeline.
    target: str | None = Query(default=None, max_length=2048),
    # Over the whole history, so paging stays right; newest first by default.
    sort: Literal["created_at", "target", "risk_score", "verdict", "status"] = Query(default="created_at"),
    order: Literal["asc", "desc"] = Query(default="desc"),
) -> ScanHistoryResponse:
    # Admins see every scan, including ones from before accounts existed; users only their own.
    owner_id = None if viewer.is_admin else viewer.user_id
    rows, total = list_jobs(limit, offset, owner_id=owner_id, target=target, sort=sort, order=order)
    rescans = _Rescans(viewer)
    items = [
        ScanSummaryResponse(
            id=row["id"],
            report_no=row["report_no"],
            target=row["target"],
            status=row["status"],
            created_at=row["created_at"],
            finished_at=row["finished_at"],
            error=row["error"],
            risk_score=row["risk_score"],
            severity=row["severity"],
            recommendation=row["recommendation"],
            ai_review=row["ai_review"],
            completed_steps=(
                TOTAL_GRAPH_STEPS
                if row["status"] == JobStatus.DONE
                else listed_progress(row["id"], row["completed_steps"])
            ),
            total_steps=TOTAL_GRAPH_STEPS,
            rescan=rescans.allowed(row),
        )
        for row in rows
    ]
    return ScanHistoryResponse(items=items, total=total)


def _visible_scan(job_id: str, viewer: Viewer, *, content: bool = True) -> dict:
    """404, not 403, for someone else's scan, so ids can't be probed. A scan of a private
    repository's content (its report, logs, a share link, a rescan with its owner's connection) is
    its owner's alone: an admin sees that it exists, and may delete it or revoke its link
    (content=False), but not open it. Returns its row, so callers don't read it again."""
    scan = db.get_scan(job_id)
    if scan is None or not viewer.can_see(scan):
        raise HTTPException(status_code=404, detail="inspection not found")
    if content and scan.get("private_source") and scan.get("owner_id") != viewer.user_id:
        raise HTTPException(status_code=403, detail="This inspection read a private repository: only the person who started it can open it")
    return scan


@router.get("/{job_id}", response_model=ScanStatusResponse)
def read_scan(job_id: str, viewer: ScanViewer) -> ScanStatusResponse:
    scan = _visible_scan(job_id, viewer)
    response = _to_response(job_from_row(scan))
    response.rescan = _Rescans(viewer).allowed(scan)
    response.shared = sharing.is_shared(scan)
    response.share_token = sharing.stored_token(scan)
    response.badge = bool(scan.get("badge"))
    response.private_source = bool(scan.get("private_source"))
    compared = rescan.comparison_for(scan)
    if compared is not None:
        response.comparison, before = compared
        if response.result and response.result.get("issues"):
            response.result = {**response.result, "issues": rescan.mark_changes(response.result["issues"], before)}
    return response


@router.get("/{job_id}/skills/{index}", response_model=dict)
def read_scan_skill(job_id: str, index: int, viewer: ScanViewer) -> dict:
    """The report of one skill in a scan of a repository holding several, its findings marked new or
    unchanged when the scan has a previous one."""
    scan = _visible_scan(job_id, viewer)
    skills = (scan.get("result") or {}).get("skills") or []
    if not 0 <= index < len(skills) or "report" not in skills[index]:
        raise HTTPException(status_code=404, detail="skill not found")
    report = skills[index]["report"]
    compared = rescan.comparison_for(scan)
    if compared is not None:
        report = {**report, "issues": rescan.mark_changes(report.get("issues") or [], compared[1], skills[index].get("path"))}
    return report


ExportFormat = Literal["json", "sarif"]


def export_response(scan: dict, format: ExportFormat) -> Response:
    """The scan's finished report as a download: skillspector's JSON, or SARIF (app/exports.py)."""
    if scan["status"] != JobStatus.DONE or not scan.get("result"):
        raise HTTPException(status_code=409, detail="Only a finished inspection's report can be downloaded")
    document = exports.sarif(scan["result"]) if format == "sarif" else scan["result"]
    name = exports.filename(scan["target"], "sarif" if format == "sarif" else "json")
    return Response(
        exports.as_bytes(document),
        media_type=exports.SARIF_MEDIA_TYPE if format == "sarif" else "application/json",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/{job_id}/export")
def export_scan(job_id: str, viewer: ScanViewer, format: Annotated[ExportFormat, Query()] = "json") -> Response:
    scan = _visible_scan(job_id, viewer)
    return export_response(scan, format)


class ShareResponse(BaseModel):
    # None when the result is shared already and its link can't be shown again: only whoever saved
    # it has it, and `renew` makes a new one.
    token: str | None
    # Whether the link can be shown again later (it's kept encrypted, with SECRET_KEY).
    kept: bool


class PrivateConfirm(BaseModel):
    # Required to share, or badge, a scan of a private repository: its result becomes public.
    confirm_private: bool = False


class ShareRequest(PrivateConfirm):
    # Replace the link with a new one: the old one stops working.
    renew: bool = False


def _confirmed_if_private(scan: dict, confirm: PrivateConfirm | None, what: str) -> None:
    if scan.get("private_source") and not (confirm and confirm.confirm_private):
        raise HTTPException(status_code=409, detail=f"This inspection read a private repository: confirm that its report may be {what}")


@router.post("/{job_id}/share", response_model=ShareResponse)
def share_scan(job_id: str, viewer: CurrentViewer, req: Annotated[ShareRequest | None, Body()] = None) -> ShareResponse:
    """A read-only link to the result, for anyone who has it, until it's revoked. Sharing again
    gives the same link when it's kept (app/sharing.py); `renew` replaces it."""
    req = req or ShareRequest()
    scan = _visible_scan(job_id, viewer)
    if scan["status"] != JobStatus.DONE:
        raise HTTPException(status_code=409, detail="Only a finished inspection's report can be shared")
    kept = secrets_box.is_configured()
    if sharing.is_shared(scan):
        if not req.renew:
            token = sharing.stored_token(scan)
            return ShareResponse(token=token, kept=token is not None)
    else:
        _confirmed_if_private(scan, req, "shared")
    token = sharing.create(job_id)
    audit(viewer.user, "scan.shared", detail=f"{scan['target']} (new link)" if req.renew else scan["target"])
    return ShareResponse(token=token, kept=kept)


@router.delete("/{job_id}/share", status_code=204)
def unshare_scan(job_id: str, viewer: CurrentViewer) -> None:
    """Revoke the result's link: it stops working at once. Sharing again makes a new one."""
    scan = _visible_scan(job_id, viewer, content=False)
    if sharing.is_shared(scan):
        sharing.revoke(job_id)
        audit(viewer.user, "scan.unshared", detail=scan["target"])


@router.post("/{job_id}/badge", status_code=204)
def add_to_badge(job_id: str, viewer: CurrentViewer, confirm: Annotated[PrivateConfirm | None, Body()] = None) -> None:
    """Show the shared result on its target's public status badge (/badge?target=…): the badge
    shows the latest scan of the target put on it, by anyone."""
    scan = _visible_scan(job_id, viewer)
    if not sharing.is_shared(scan):
        raise HTTPException(status_code=409, detail="Share the report first: the badge links to it")
    if uploads.is_upload_target(scan["target"]):
        raise HTTPException(status_code=422, detail="An uploaded file has no link for a badge to name")
    if scan.get("baseline") is not None or ((scan.get("result") or {}).get("applied_baseline")):
        # Its baseline's accepted findings don't count, so the badge would read safer than the skill.
        raise HTTPException(status_code=422, detail="An inspection with a baseline can't be on a badge: inspect the skill without one")
    _confirmed_if_private(scan, confirm, "shown on a public badge")
    if not scan.get("badge"):
        db.set_badge(job_id, True)
        audit(viewer.user, "scan.badge_added", detail=scan["target"])


@router.delete("/{job_id}/badge", status_code=204)
def remove_from_badge(job_id: str, viewer: CurrentViewer) -> None:
    """Take the result off the badge, which then shows the target's previous scan on it, if any."""
    scan = _visible_scan(job_id, viewer, content=False)
    if scan.get("badge"):
        db.set_badge(job_id, False)
        audit(viewer.user, "scan.badge_removed", detail=scan["target"])


@router.post("/{job_id}/rescan", response_model=ScanQueuedResponse, dependencies=[Depends(_rate_limit_scan)])
async def rescan_target(job_id: str, viewer: ScanViewer) -> ScanQueuedResponse:
    """Scan a scan's target again, as it was scanned: the result is compared with this one. Like any
    scan, it counts towards the viewer's quotas."""
    target, options = await asyncio.to_thread(_rescan_options, job_id, viewer)
    return await queue_scan(target, options, viewer)


def _rescan_options(job_id: str, viewer: Viewer) -> tuple[str, ScanOptions]:
    scan = _visible_scan(job_id, viewer)
    if uploads.is_upload_target(scan["target"]):
        raise HTTPException(status_code=422, detail="An uploaded file isn't kept once inspected: upload it again to re-inspect it")
    try:
        llm = _Rescans(viewer).llm(scan)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    options = ScanOptions(
        llm=llm,
        baseline=scan.get("baseline"),
        use_shipped_baseline=bool(scan.get("use_shipped_baseline")),
        transitive_depth=scan.get("transitive_depth"),
    )
    return scan["target"], options


@router.get("/{job_id}/baseline", response_model=BaselineResponse)
def read_scan_baseline(
    job_id: str,
    viewer: ScanViewer,
    reason: str | None = Query(default=None, max_length=500),
) -> BaselineResponse:
    """A baseline accepting every active finding of the scan, made while it ran (app/scan_runner.py)."""
    scan = _visible_scan(job_id, viewer)
    baseline = ((scan or {}).get("result") or {}).get("generated_baseline")
    if not baseline:
        raise HTTPException(status_code=404, detail="This inspection has no baseline to download")
    if reason and reason.strip():
        baseline = {**baseline, "fingerprints": [{**entry, "reason": reason.strip()} for entry in baseline["fingerprints"]]}
    # Written by skillspector itself, header included, as `skillspector baseline` would.
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, SHIPPED_NAME)
        dump_baseline(baseline, path)
        with open(path, encoding="utf-8") as file:
            content = file.read()
    return BaselineResponse(filename=SHIPPED_NAME, content=content)


@router.get("/{job_id}/logs", response_model=ScanLogsResponse)
def read_scan_logs(job_id: str, viewer: ScanViewer, after: int = Query(default=0, ge=0)) -> ScanLogsResponse:
    """The scan's log lines after cursor `after`: all of them at first, then only new ones."""
    _visible_scan(job_id, viewer)
    lines, cursor = get_logs_after(job_id, after)
    return ScanLogsResponse(lines=lines, cursor=cursor)


@router.delete("/{job_id}", status_code=204)
def delete_scan(job_id: str, viewer: CurrentViewer) -> None:
    _visible_scan(job_id, viewer, content=False)
    if not delete_job(job_id):
        raise HTTPException(status_code=404, detail="inspection not found")
