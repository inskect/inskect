"""A target's status badge: the verdict of the latest scan of it that its owner put on the badge.

A scan's owner puts a shared result on its target's badge from the share dialog (POST
/scan/{id}/badge); revoking the link takes it off. Nothing else feeds a badge: a private scan, or
one only shared by link, never shows. Nor does a scan with a baseline, whose accepted findings
don't count, or an upload, which has no link. The web app renders the SVG (server/routes/badge.get.ts)
and caches it; this lookup is one indexed query, and never starts a scan.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app import db, sharing
from app.targets import mcp_entry_url, raw_file_url

router = APIRouter(prefix="/badge", tags=["badge"])


class BadgeResponse(BaseModel):
    # All None when no scan of the target is on its badge.
    recommendation: str | None = None
    risk_score: float | None = None
    scanned_at: float | None = None
    # The shared result the badge links to (/shared/{token}): a badge link (app/sharing.py), which
    # opens it for as long as it's on the badge.
    share_token: str | None = None


def stored_target(target: str) -> str:
    """The target as a scan of it is stored (ScanRequest.validate_target), so the link a README
    gives finds the scans of it."""
    target = target.strip()
    return mcp_entry_url(target) or raw_file_url(target)


@router.get("", response_model=BadgeResponse)
def read_badge(target: str = Query(min_length=1, max_length=2048)) -> BadgeResponse:
    scan = db.badge_scan(stored_target(target))
    if scan is None:
        return BadgeResponse()
    return BadgeResponse(
        recommendation=scan.get("recommendation"),
        risk_score=scan.get("risk_score"),
        scanned_at=scan.get("finished_at") or scan.get("created_at"),
        share_token=sharing.badge_link(scan),
    )
