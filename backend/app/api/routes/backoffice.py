import time

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app import auth, db, monitoring
from app.api.routes.users import ActivityEntry
from app.auth.deps import AdminViewer

router = APIRouter(prefix="/admin", tags=["admin"])

_WEEK_SECONDS = 7 * 86400


class UserStats(BaseModel):
    total: int
    admins: int
    suspended: int
    new: int


class ScanStats(BaseModel):
    total: int
    recent: int
    do_not_install: int
    caution: int
    safe: int
    failed: int
    active: int


class HealthError(BaseModel):
    kind: str
    message: str | None
    at: float
    scan_id: str | None


class HealthAlert(BaseModel):
    rule: str | None
    # The rule's title, while it's still registered.
    title: str | None = None
    at: float


class EventCount(BaseModel):
    """Events of a kind an alert rule labels (monitoring.Rule.label)."""

    kind: str
    label: str
    count: int


class Health(BaseModel):
    """What went wrong over the last `hours` (app/monitoring.py)."""

    hours: int
    finished: int
    failed: int
    last_error: HealthError | None
    # Where alerts go: "webhook", "email"; empty when they aren't set up.
    alert_channels: list[str]
    # The web app sits behind a proxy it doesn't trust (app/proxy.py): visitors share rate limits.
    proxy_warning: str | None = None
    last_alert: HealthAlert | None
    # The labelled kinds' events over the same hours.
    events: list[EventCount] = []


class Overview(BaseModel):
    auth: str
    email_enabled: bool
    signup_allowed: bool
    # "new" and "recent" count the last 7 days.
    users: UserStats
    scans: ScanStats
    recent_activity: list[ActivityEntry]
    health: Health


class ActivityPage(BaseModel):
    items: list[ActivityEntry]
    total: int


@router.get("/overview", response_model=Overview)
def read_overview(viewer: AdminViewer) -> Overview:
    stats = db.overview_stats(since=time.time() - _WEEK_SECONDS)
    activity, _ = db.list_audit(8, 0)
    return Overview(
        auth=auth.auth_mode(),
        email_enabled=auth.email_enabled(),
        signup_allowed=auth.signup_allowed(),
        users=UserStats(**stats["users"]),
        scans=ScanStats(**stats["scans"]),
        recent_activity=[ActivityEntry(**entry) for entry in activity],
        health=Health(**monitoring.health()),
    )


class AlertTestResponse(BaseModel):
    channels: list[str]


@router.post("/alerts/test", response_model=AlertTestResponse)
def send_test_alert(viewer: AdminViewer) -> AlertTestResponse:
    """Send a test alert to every channel set up, to check they're reached."""
    if not monitoring.channels():
        raise HTTPException(status_code=409, detail="Alerts aren't set up: set INSKECT_ALERT_WEBHOOK_URL or INSKECT_ALERT_EMAIL")
    sent = monitoring.send_alert("Test alert", "Alerts from this server reach you here.")
    if not sent:
        raise HTTPException(status_code=502, detail="The alert couldn't be sent: the server's log has why")
    return AlertTestResponse(channels=sent)


@router.get("/activity", response_model=ActivityPage)
def read_activity(
    viewer: AdminViewer,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ActivityPage:
    rows, total = db.list_audit(limit, offset)
    return ActivityPage(items=[ActivityEntry(**row) for row in rows], total=total)


class AlertRule(BaseModel):
    name: str
    title: str
    kind: str
    label: str | None = None
    condition: str
    cooldown_minutes: int
    # False for a rule that doesn't apply here, such as one about accounts without them.
    applies: bool
    tripped: bool
    current: str | None
    last_alert_at: float | None
    # Set while the rule waits out its cooldown after an alert.
    quiet_until: float | None


class AlertChannels(BaseModel):
    # The webhook's host only: its path is its secret.
    webhook_host: str | None
    emails: list[str]
    email_ready: bool


class Monitoring(BaseModel):
    health: Health
    rules: list[AlertRule]
    channels: AlertChannels


# The windows the page offers: a day, a week, and the 30 days events are kept.
_WINDOWS = (24, 168, 720)


@router.get("/monitoring", response_model=Monitoring)
def read_monitoring(viewer: AdminViewer, hours: int = Query(default=24)) -> Monitoring:
    """The monitoring page: the window's counts, each alert rule's state, and where alerts go."""
    if hours not in _WINDOWS:
        raise HTTPException(status_code=422, detail="hours is 24, 168 or 720")
    return Monitoring(
        health=Health(**monitoring.health(hours=hours)),
        rules=[AlertRule(**rule) for rule in monitoring.rules_status()],
        channels=AlertChannels(**monitoring.channel_details()),
    )


class MonitorEvent(BaseModel):
    id: int
    created_at: float
    kind: str
    message: str | None
    scan_id: str | None
    count: int


class MonitorEventPage(BaseModel):
    items: list[MonitorEvent]
    total: int


_EVENT_FILTERS: dict[str, tuple[str, ...]] = {
    "all": (),
    "failures": (monitoring.SCAN_FAILED,),
    "lockouts": (monitoring.SIGN_IN_LOCKED,),
    "alerts": (monitoring.ALERT_SENT,),
}


@router.get("/monitoring/events", response_model=MonitorEventPage)
def read_monitor_events(
    viewer: AdminViewer,
    # One of _EVENT_FILTERS, or a kind an alert rule labels.
    kind: str = Query(default="all", max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> MonitorEventPage:
    """The events monitoring kept (30 days), newest first."""
    if kind in _EVENT_FILTERS:
        kinds = _EVENT_FILTERS[kind]
    elif kind in monitoring.labelled_kinds():
        kinds = (kind,)
    else:
        raise HTTPException(status_code=422, detail="Unknown kind of event")
    rows, total = db.list_monitor_events(limit, offset, kinds)
    return MonitorEventPage(items=[MonitorEvent(**row) for row in rows], total=total)
