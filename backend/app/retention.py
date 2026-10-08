from __future__ import annotations

import asyncio
import logging
import time

from app import db, monitoring

logger = logging.getLogger(__name__)

_SWEEP_INTERVAL_SECONDS = 3600.0
# How long the activity log keeps an entry, whatever the scans' retention (the privacy policy says so).
AUDIT_RETENTION_DAYS = 365

_task: asyncio.Task | None = None


def get_retention_days() -> float | None:
    return db.get_retention_days()


def set_retention_days(value: float | None) -> None:
    db.set_retention_days(value)
    sweep_once()


def sweep_once() -> int:
    # Monitoring events are kept a month, and the activity log a year, whatever the scans' retention.
    monitoring.prune()
    now = time.time()
    db.prune_account_records(audit_cutoff=now - AUDIT_RETENTION_DAYS * 86400, now=now)
    retention_days = db.get_retention_days()
    if retention_days is None:
        return 0
    cutoff = time.time() - retention_days * 86400
    deleted = db.delete_scans_older_than(cutoff)
    if deleted:
        logger.info("Retention sweep deleted %d scan(s) older than %s day(s)", deleted, retention_days)
    return deleted


async def _sweep_loop() -> None:
    while True:
        try:
            sweep_once()
        except Exception:
            logger.exception("Retention sweep failed; will retry on the next interval")
        await asyncio.sleep(_SWEEP_INTERVAL_SECONDS)


def start() -> None:
    global _task
    _task = asyncio.create_task(_sweep_loop())


def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
