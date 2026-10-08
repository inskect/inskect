from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.deps import require_admin
from app.claude_login import complete_claude_login, start_claude_login
from app.core.config import get_settings


def _claude_cli_allowed() -> None:
    # Off (INSKECT_CLAUDE_CLI=false), users bring their own key instead (app/claude_key.py).
    if not get_settings().claude_cli:
        raise HTTPException(status_code=404, detail="There's no server-wide Claude login on this server")


router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(_claude_cli_allowed), Depends(require_admin)]
)


class ClaudeLoginStartResponse(BaseModel):
    url: str


class ClaudeLoginCompleteRequest(BaseModel):
    code: str


class ClaudeLoginCompleteResponse(BaseModel):
    success: bool
    output: str


@router.post("/claude-login/start", response_model=ClaudeLoginStartResponse)
async def claude_login_start() -> ClaudeLoginStartResponse:
    try:
        url = await start_claude_login()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ClaudeLoginStartResponse(url=url)


@router.post("/claude-login/complete", response_model=ClaudeLoginCompleteResponse)
async def claude_login_complete(req: ClaudeLoginCompleteRequest) -> ClaudeLoginCompleteResponse:
    try:
        success, output = await complete_claude_login(req.code)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ClaudeLoginCompleteResponse(success=success, output=output)
