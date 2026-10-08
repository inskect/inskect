import logging
import os

_provider = os.environ.get("SKILLSPECTOR_PROVIDER", "").strip()
_known_working = (
    (_provider == "anthropic" and bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()))
    or (_provider == "openai" and bool(os.environ.get("OPENAI_API_KEY", "").strip()))
    or (_provider == "ollama")
)
if not _known_working:
    os.environ["SKILLSPECTOR_PROVIDER"] = "anthropic"
    os.environ["ANTHROPIC_API_KEY"] = "sk-placeholder-unlocks-llm-analyzer-wiring"

# The operator's skillspector settings, before skillspector reads them on import.
from app.analysis_settings import apply_to_process

apply_to_process()

from contextlib import asynccontextmanager
from typing import get_args

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from skillspector import __version__ as skillspector_version
from skillspector.llm_utils import is_llm_available

from app import db, proxy, retention, scan_logs, sharing, uploads
from app.api.routes import (
    account,
    admin,
    auth,
    backoffice,
    badge,
    scan,
    shared,
    users,
)
from app.api.routes import settings as settings_routes
from app.auth import auth_mode
from app.claude_login import claude_cli_enabled, kill_pending
from app.core.config import LLMProvider, get_settings
from app.db import init_db
from app.jobs import get_runner
from app.models import model_catalog
from app.scan_logs import init_logging
from app.scanner import get_executor, provider_allowed

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("INSKECT_ADMIN_TOKEN"):
        logging.getLogger("uvicorn.error").warning(
            "INSKECT_ADMIN_TOKEN is no longer used and can be removed. "
            "Admin access now follows INSKECT_AUTH: with 'none' (the default) anyone who can "
            "reach the server has full access; with 'accounts', admins sign in."
        )
    init_db()
    # Links stored as they were before they were hashed (app/sharing.py).
    sharing.hash_plain_tokens()
    # The replaceable pieces (app/core/extensions.py), loaded now: a setting naming one that can't
    # be loaded stops the API here rather than at the first scan.
    get_executor()
    uploads.get_store()
    get_runner().on_startup()
    init_logging()
    # Off when something else runs the sweep on a schedule (INSKECT_RETENTION_LOOP).
    if settings.retention_loop:
        retention.start()
    yield
    retention.stop()
    kill_pending()
    # Lines a scan logged in its last second, before they're lost with the process.
    scan_logs.close()


# The release, stamped into the image from its Git tag at build time (.github/workflows/release.yml);
# "dev" for anything built from a checkout.
VERSION = os.environ.get("INSKECT_VERSION") or "dev"

app = FastAPI(title="Inskect API", version=VERSION, lifespan=lifespan)

app.middleware("http")(proxy.check_caller)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI's default 422 echoes the submitted values back, which for a scan request includes
    the API key. Keep where and why, drop what was sent."""
    errors = [{k: v for k, v in error.items() if k not in ("input", "ctx", "url")} for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


app.include_router(auth.router)
app.include_router(account.router)
app.include_router(users.router)
app.include_router(backoffice.router)
app.include_router(scan.router)
app.include_router(shared.router)
app.include_router(badge.router)
app.include_router(admin.router)
app.include_router(settings_routes.router)


@app.get("/models")
def models() -> dict:
    """The models skillspector knows per provider, for the scan form's model picker."""
    return model_catalog()


@app.get("/health")
def health() -> dict:
    llm_available, _ = is_llm_available()
    return {
        "status": "ok",
        "version": VERSION,
        "auth": auth_mode(),
        "skillspector_version": skillspector_version,
        "llm_available": llm_available,
        "claude_cli_available": claude_cli_enabled(),
        # The AI providers scans may use, and whether a scan may set its own endpoint.
        "ai_providers": [provider for provider in get_args(LLMProvider) if provider_allowed(provider, settings)],
        "allow_custom_ai_url": settings.allow_custom_ai_url,
        # The deepest a scan may follow a skill's external references; 0 when it can't.
        "transitive_max_depth": settings.transitive_max_depth,
        # Where an uploaded file goes (app/uploads.py), and the largest it takes.
        "upload_store": uploads.store_kind(settings),
        "max_upload_bytes": uploads.max_bytes(),
        # How long data is kept, for a privacy policy to say; scans' is None when they're kept until deleted.
        "retention": _retention(),
    }


def _retention() -> dict | None:
    try:
        scan_days = db.get_retention_days()
    except Exception:  # noqa: BLE001 - the database is down: health says so elsewhere
        return None
    return {"scan_days": scan_days, "session_days": settings.session_days, "activity_days": retention.AUDIT_RETENTION_DAYS}
