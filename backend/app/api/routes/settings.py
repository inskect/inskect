from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app import auth, db, quotas, retention
from app.auth.deps import AdminViewer

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    scan_retention_days: float | None
    # Whether visitors may create their own account; always false without accounts.
    allow_signup: bool
    # Whether new scans are refused, for everyone.
    scans_paused: bool
    # Per signed-in user other than admins; null means no limit.
    daily_scan_quota: int | None
    concurrent_scan_quota: int | None


class UpdateSettingsRequest(BaseModel):
    """Only the fields sent are changed. A quota sent as null means no limit."""

    scan_retention_days: float | None = None
    allow_signup: bool | None = None
    scans_paused: bool | None = None
    daily_scan_quota: int | None = Field(default=None, ge=1)
    concurrent_scan_quota: int | None = Field(default=None, ge=1)

    @field_validator("scan_retention_days")
    @classmethod
    def validate_positive(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("scan_retention_days must be positive, or null to keep inspections forever")
        return value


def _current() -> SettingsResponse:
    limits = quotas.current()
    return SettingsResponse(
        scan_retention_days=retention.get_retention_days(),
        allow_signup=auth.signup_allowed(),
        scans_paused=limits.paused,
        daily_scan_quota=limits.daily,
        concurrent_scan_quota=limits.concurrent,
    )


def _quota_detail(limits: quotas.ScanLimits) -> str:
    daily = "no daily limit" if limits.daily is None else f"{limits.daily} a day"
    concurrent = "no limit at once" if limits.concurrent is None else f"{limits.concurrent} at once"
    return f"{daily}, {concurrent}"


@router.get("", response_model=SettingsResponse)
def read_settings() -> SettingsResponse:
    return _current()


@router.put("", response_model=SettingsResponse)
def update_settings(req: UpdateSettingsRequest, viewer: AdminViewer) -> SettingsResponse:
    sent = req.model_fields_set
    if "scan_retention_days" in sent and req.scan_retention_days != retention.get_retention_days():
        retention.set_retention_days(req.scan_retention_days)
        days = req.scan_retention_days
        auth.audit(viewer.user, "settings.retention_changed", detail="keep forever" if days is None else f"{days:g} days")
    if "allow_signup" in sent and req.allow_signup is not None and req.allow_signup != auth.signup_allowed():
        db.set_allow_signup(req.allow_signup)
        auth.audit(viewer.user, "settings.signup_changed", detail="on" if req.allow_signup else "off")

    limits = quotas.current()
    changed = quotas.ScanLimits(
        paused=req.scans_paused if "scans_paused" in sent and req.scans_paused is not None else limits.paused,
        daily=req.daily_scan_quota if "daily_scan_quota" in sent else limits.daily,
        concurrent=req.concurrent_scan_quota if "concurrent_scan_quota" in sent else limits.concurrent,
    )
    if changed != limits:
        quotas.save(changed)
        if changed.paused != limits.paused:
            auth.audit(viewer.user, "settings.scans_paused" if changed.paused else "settings.scans_resumed")
        if (changed.daily, changed.concurrent) != (limits.daily, limits.concurrent):
            auth.audit(viewer.user, "settings.quotas_changed", detail=_quota_detail(changed))
    return _current()
