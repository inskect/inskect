"""Monitoring: what's going wrong, in the logs, the backoffice, and alerts.

Each event is written three ways:

- a structured log line (JSON, `"event": "inskect.<kind>"`) on stdout, for a log drain or
  `docker compose logs`;
- for the ones worth counting, a row in monitor_events, which the backoffice's health panel reads;
- when a rule below trips, an alert to INSKECT_ALERT_WEBHOOK_URL and/or by email to
  INSKECT_ALERT_EMAIL, at most once per rule per cooldown.

Alerts carry what went wrong, scrubbed of keys, tokens, email addresses and URL paths (scrub()):
never a scan's target, a user, or a key. They're sent from whichever process saw the event; with
several, two may both send one now and then.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app import db, mail, proxy
from app.auth import auth_mode
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Counted kinds.
SCAN_FAILED = "scan_failed"
SIGN_IN_LOCKED = "sign_in_locked"
ALERT_SENT = "alert_sent"
ERROR_KINDS = (SCAN_FAILED,)

KEEP_DAYS = 30
_MESSAGE_LIMIT = 500
_WEBHOOK_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class Measure:
    """Where a rule stands now: whether it trips, the numbers it read, and what an alert says."""

    tripped: bool
    current: str
    alert: str


@dataclass(frozen=True)
class Rule:
    name: str
    title: str
    # What trips it, for the monitoring page.
    condition: str
    # The event that makes it check.
    kind: str
    window_seconds: float
    cooldown_seconds: float
    measure: Callable[[float, str | None], Measure]
    # Only with sign-in: accounts to guess the passwords of.
    accounts_only: bool = False


# Failure rate: at least this many failures, and at least this share of the scans that finished.
FAILURE_MIN = 3
FAILURE_SHARE = 0.5
_HALF_HOUR = 30 * 60


def _plural(count: int, word: str, plural: str | None = None) -> str:
    return f"{count} {word if count == 1 else plural or word + 's'}"


def _failures(now: float, message: str | None) -> Measure:
    outcomes = db.scan_outcomes(since=now - _HALF_HOUR)
    failed, finished = outcomes["failed"], outcomes["finished"]
    tripped = failed >= FAILURE_MIN and failed / max(finished, 1) >= FAILURE_SHARE
    if message is None and failed:
        last = db.last_monitor_event(SCAN_FAILED)
        message = last["message"] if last else None
    return Measure(
        tripped,
        f"{failed} of {_plural(finished, 'finished inspection')} failed in the last 30 minutes",
        f"{failed} of the {finished} inspections that finished in the last 30 minutes failed. The last error: {message}",
    )


def _lockouts(now: float, message: str | None) -> Measure:
    count = db.monitor_counts(since=now - 60 * 60).get(SIGN_IN_LOCKED, 0)
    return Measure(
        count > 0,
        f"{_plural(count, 'lockout')} in the last hour",
        f"Sign-ins to an account were locked {_plural(count, 'time')} in the last hour, after too many failed attempts wherever they came from: someone may be guessing passwords. The backoffice's activity log says which accounts.",
    )


FAILURE_RULE = Rule(
    "failure_rate", "Many inspections are failing",
    f"At least {FAILURE_MIN} inspections failed in 30 minutes, and at least {FAILURE_SHARE:.0%} of those that finished",
    SCAN_FAILED, _HALF_HOUR, 60 * 60, _failures,
)
LOCKOUT_RULE = Rule(
    "sign_in_lockouts", "Accounts are hitting the failed sign-in limit", "An account has 5 failed sign-ins in 15 minutes, 10 in an hour or 20 in a day",
    SIGN_IN_LOCKED, 60 * 60, 60 * 60, _lockouts, accounts_only=True,
)
_rules: list[Rule] = [FAILURE_RULE, LOCKOUT_RULE]


def register_rule(rule: Rule) -> None:
    """Add an alert rule to the built-in ones, checked when an event of its kind is recorded
    (record()) and shown on the Monitoring page: for an extension's own events (docs/EXTENDING.md)."""
    if any(existing.name == rule.name for existing in _rules):
        raise ValueError(f"an alert rule is already named {rule.name}")
    _rules.append(rule)


def rules() -> tuple[Rule, ...]:
    return tuple(_rules)

_SECRETS = [
    re.compile(r"sk-ant-[\w-]+"),
    re.compile(r"\bsk-[\w-]{16,}"),
    re.compile(r"\bsst_[\w-]+"),
    re.compile(r"\b(?:ghp|gho|ghs|ghu|github_pat)_\w+"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\bbearer\s+[\w.~+/=-]+"),
    re.compile(r"(?i)\b(api[_-]?key|token|password|secret)=[^\s&]+"),
]
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"\b(https?)://([^/\s?#'\"<>)]+)([^\s'\"<>)]*)")


def _host_only(match: re.Match[str]) -> str:
    return f"{match[1]}://{match[2]}" + ("/…" if match[3].strip("/") else "")


def scrub(text: str | None) -> str | None:
    """A message fit for an alert or a log: no keys or tokens, no email addresses, and URLs cut
    to their host, which leaves out which repository or file a user scanned."""
    if text is None:
        return None
    for pattern in _SECRETS:
        text = pattern.sub("[redacted]", text)
    text = _EMAIL.sub("[email]", text)
    text = _URL.sub(_host_only, text)
    return text[:_MESSAGE_LIMIT]


def log_event(kind: str, **fields: Any) -> None:
    """One JSON line on stdout. Fields are ids, counts and scrubbed messages, never user data."""
    line = {"event": f"inskect.{kind}", "at": round(time.time(), 3), **{key: value for key, value in fields.items() if value is not None}}
    print(json.dumps(line, ensure_ascii=False), file=sys.stdout, flush=True)


def record(kind: str, message: str | None = None, *, scan_id: str | None = None, count: int = 1, **fields: Any) -> None:
    """Log a counted event, store it, and alert if a rule trips. Never raises: monitoring mustn't
    break what it watches. Blocking (it may send an alert): async code calls it in a thread."""
    message = scrub(message)
    log_event(kind, scan_id=scan_id, message=message, count=count if count != 1 else None, **fields)
    try:
        db.add_monitor_event(created_at=time.time(), kind=kind, message=message, scan_id=scan_id, count=count)
        _check(kind, message)
    except Exception:
        logger.warning("Couldn't record the %s monitoring event", kind, exc_info=True)


def _check(kind: str, message: str | None) -> None:
    now = time.time()
    for rule in _rules:
        if rule.kind == kind:
            measure = rule.measure(now, message)
            if measure.tripped:
                _alert(rule, measure.alert, now)


def _alert(rule: Rule, text: str, now: float) -> None:
    last = db.last_monitor_event(ALERT_SENT, message=rule.name)
    if last is not None and now - last["created_at"] < rule.cooldown_seconds:
        return
    channels = send_alert(rule.title, text)
    if channels:
        db.add_monitor_event(created_at=now, kind=ALERT_SENT, message=rule.name, scan_id=None, count=1)


def channels(settings: Settings | None = None) -> list[str]:
    """Where alerts go: 'webhook', 'email', both or neither."""
    settings = settings or get_settings()
    found = []
    if settings.alert_webhook_url:
        found.append("webhook")
    if settings.alert_email and mail.is_configured(settings):
        found.append("email")
    return found


def send_alert(title: str, text: str, settings: Settings | None = None) -> list[str]:
    """Send an alert to every channel set up; the ones it reached."""
    settings = settings or get_settings()
    sent = []
    link = mail.public_link("/admin") if settings.public_url else None
    body = f"{text}\n\nThe backoffice's overview has the details: {link}" if link else text
    if settings.alert_webhook_url:
        payload = {
            # Slack reads `text`, Discord `content`; other endpoints get both, and the fields.
            "text": f"*Inskect: {title}*\n{body}",
            "content": f"**Inskect: {title}**\n{body}",
            "title": title,
            "message": text,
            "link": link,
        }
        request = urllib.request.Request(
            settings.alert_webhook_url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "inskect"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=_WEBHOOK_TIMEOUT_SECONDS):
                sent.append("webhook")
        except (OSError, ValueError) as exc:
            logger.warning("Couldn't send an alert to the webhook: %s", exc)
    if settings.alert_email and mail.is_configured(settings):
        for address in (part.strip() for part in settings.alert_email.split(",")):
            if not address:
                continue
            try:
                mail.send(address, f"Inskect: {title}", body, settings)
                if "email" not in sent:
                    sent.append("email")
            except OSError as exc:
                logger.warning("Couldn't email an alert: %s", exc)
    log_event("alert", title=title, channels=sent)
    return sent


def health(*, hours: int = 24) -> dict[str, Any]:
    """The backoffice's health panel: the last day's failures, the last error, and where alerts go."""
    since = time.time() - hours * 3600
    outcomes = db.scan_outcomes(since=since)
    last_error = db.last_monitor_event(*ERROR_KINDS)
    last_alert = db.last_monitor_event(ALERT_SENT)
    return {
        "hours": hours,
        "finished": outcomes["finished"],
        "failed": outcomes["failed"],
        "last_error": (
            {"kind": last_error["kind"], "message": last_error["message"], "at": last_error["created_at"], "scan_id": last_error["scan_id"]}
            if last_error
            else None
        ),
        "alert_channels": channels(),
        "proxy_warning": proxy.warning(),
        "last_alert": {"rule": last_alert["message"], "at": last_alert["created_at"]} if last_alert else None,
    }


def rules_status(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Each alert rule: what trips it, where it stands now, and when it last alerted."""
    settings = settings or get_settings()
    now = time.time()
    status = []
    for rule in _rules:
        applies = not rule.accounts_only or auth_mode(settings) == "accounts"
        measure = rule.measure(now, None) if applies else None
        last = db.last_monitor_event(ALERT_SENT, message=rule.name)
        quiet_until = last["created_at"] + rule.cooldown_seconds if last else None
        status.append({
            "name": rule.name,
            "title": rule.title,
            "condition": rule.condition,
            "cooldown_minutes": round(rule.cooldown_seconds / 60),
            "applies": applies,
            "tripped": bool(measure and measure.tripped),
            "current": measure.current if measure else None,
            "last_alert_at": last["created_at"] if last else None,
            "quiet_until": quiet_until if quiet_until and quiet_until > now else None,
        })
    return status


def channel_details(settings: Settings | None = None) -> dict[str, Any]:
    """Where alerts go, for an admin: the webhook by its host only (its path is its secret), and
    the email addresses, with whether email can be sent."""
    settings = settings or get_settings()
    webhook_host = None
    if settings.alert_webhook_url:
        match = _URL.match(settings.alert_webhook_url)
        webhook_host = match[2] if match else "set"
    emails = [part.strip() for part in (settings.alert_email or "").split(",") if part.strip()]
    return {"webhook_host": webhook_host, "emails": emails, "email_ready": mail.is_configured(settings)}


def prune() -> int:
    return db.delete_monitor_events_older_than(time.time() - KEEP_DAYS * 86400)
