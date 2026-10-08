"""A shared result, read-only, for anyone with its link: no sign-in, with accounts or without.

A scan's owner (or an admin) shares it from its result page (POST /scan/{id}/share), and the link
works until they revoke it. A shared result leaves out what belongs to their account: how many AI
tokens it used, the comparison with their previous scan of the target, and what they could do with
it (rescan, share). Each address may open a limited number of shared pages a minute, which keeps
anyone from trying tokens, though at 192 random bits there's nothing to find.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app import rate_limit, sharing
from app.api.routes.scan import (
    ExportFormat,
    ScanStatusResponse,
    _to_response,
    export_response,
)
from app.scanner import job_from_row

# Pages and downloads per address per minute.
SHARED_RATE_LIMIT = 120


def _rate_limit_shared(request: Request) -> None:
    rate_limit.enforce(f"shared:{rate_limit.client_key(request)}", SHARED_RATE_LIMIT, 60.0, "Too many requests for shared results")


router = APIRouter(prefix="/shared", tags=["shared"], dependencies=[Depends(_rate_limit_shared)])


def _shared_scan(token: str) -> dict:
    scan = sharing.find(token) if token else None
    if scan is None:
        raise HTTPException(status_code=404, detail="This link doesn't exist, or it was revoked")
    return scan


@router.get("/{token}", response_model=ScanStatusResponse)
def read_shared_scan(token: str) -> ScanStatusResponse:
    response = _to_response(job_from_row(_shared_scan(token)))
    response.ai_tokens = None
    return response


@router.get("/{token}/skills/{index}", response_model=dict)
def read_shared_skill(token: str, index: int) -> dict:
    skills = (_shared_scan(token).get("result") or {}).get("skills") or []
    if not 0 <= index < len(skills) or "report" not in skills[index]:
        raise HTTPException(status_code=404, detail="skill not found")
    return skills[index]["report"]


@router.get("/{token}/export")
def export_shared_scan(token: str, format: Annotated[ExportFormat, Query()] = "json") -> Response:
    return export_response(_shared_scan(token), format)
