"""FastAPI dependencies that resolve the request's Viewer."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException

from app.auth import ANONYMOUS_ADMIN, Viewer, api_tokens, auth_mode, user_for_token


def bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def current_viewer(authorization: str | None = Header(default=None)) -> Viewer:
    """Everyone is an admin without accounts; with accounts, a valid session is required. An API
    token doesn't do here: it only starts and reads scans (scan_viewer)."""
    if auth_mode() == "none":
        return ANONYMOUS_ADMIN
    token = bearer_token(authorization)
    if token and api_tokens.is_api_token(token):
        raise HTTPException(status_code=403, detail="An API token can only start and read inspections: sign in for the rest")
    user = user_for_token(token) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to continue")
    return Viewer(user=user, is_admin=user["role"] == "admin")


def require_admin(authorization: str | None = Header(default=None)) -> Viewer:
    viewer = current_viewer(authorization)
    if not viewer.is_admin:
        raise HTTPException(status_code=403, detail="Only an admin can do this")
    return viewer


def scan_viewer(authorization: str | None = Header(default=None)) -> Viewer:
    """As current_viewer, or an API token with the scan scope, as the user it belongs to."""
    token = bearer_token(authorization)
    if auth_mode() == "none" or not token or not api_tokens.is_api_token(token):
        return current_viewer(authorization)
    found = api_tokens.authenticate(token)
    if found is None:
        raise HTTPException(status_code=401, detail="This API token is invalid, expired or revoked")
    user, scopes = found
    if "scan" not in scopes:
        raise HTTPException(status_code=403, detail="This API token can't start or read inspections")
    return Viewer(user=user, is_admin=user["role"] == "admin", scopes=scopes)


CurrentViewer = Annotated[Viewer, Depends(current_viewer)]
# For the scan endpoints an API token may use: starting, reading, exporting and rescanning scans.
ScanViewer = Annotated[Viewer, Depends(scan_viewer)]
AdminViewer = Annotated[Viewer, Depends(require_admin)]
