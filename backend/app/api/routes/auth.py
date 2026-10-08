from typing import Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Request,
    Response,
)
from pydantic import BaseModel, Field

from app import auth, claude_key, db, quotas, rate_limit, repo_connections, uploads
from app.auth import github_sign_in, login_throttle
from app.auth.deps import CurrentViewer, bearer_token
from app.core.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    status: str
    created_at: float
    last_login_at: float | None


class ServerFeatures(BaseModel):
    """What this server offers, for the landing page to describe it as it is."""

    # Uploading a .zip or SKILL.md to scan (app/uploads.py).
    uploads: bool
    # Connecting GitHub to scan private repositories (app/repo_connections.py).
    github: bool
    # Each user's scans per 24 hours and at once; None for no limit (app/quotas.py).
    daily_quota: int | None
    concurrent_quota: int | None


def _features() -> ServerFeatures:
    limits = quotas.current()
    return ServerFeatures(
        uploads=bool(uploads.store_kind()),
        github=repo_connections.available(),
        daily_quota=limits.daily,
        concurrent_quota=limits.concurrent,
    )


class SessionResponse(BaseModel):
    auth: str
    user: UserResponse | None
    # Accounts are on but none exists yet: the first visitor creates the admin.
    needs_setup: bool
    signup_allowed: bool
    # "Forgot password?" by email is available, and sign-up confirms the address by email.
    email_enabled: bool
    # Users can save their own Claude key, and the signed-in user's saved key, if any.
    claude_key_available: bool
    claude_key: dict | None
    features: ServerFeatures


class CredentialsRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    token: str
    expires_at: float
    user: UserResponse


class SignupPendingResponse(BaseModel):
    # A link to finish signing up was emailed (or, if the address has an account, word of it).
    pending: bool = True


class ConfirmSignupRequest(BaseModel):
    token: str


def _rate_limit_login(request: Request) -> None:
    settings = get_settings()
    key = f"login:{rate_limit.client_key(request)}"
    rate_limit.enforce(key, settings.login_rate_limit, settings.login_rate_limit_window_seconds, "Too many attempts from this address")


def _require_accounts() -> None:
    if auth.auth_mode() != "accounts":
        raise HTTPException(status_code=404, detail="Accounts aren't enabled on this server")


def _signed_in(user: dict) -> TokenResponse:
    token, expires_at = auth.start_session(user["id"])
    return TokenResponse(token=token, expires_at=expires_at, user=UserResponse(**auth.public_user(user)))


def _auth_error(exc: auth.AuthError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/session", response_model=SessionResponse)
def read_session(authorization: str | None = Header(default=None)) -> SessionResponse:
    mode = auth.auth_mode()
    if mode == "none":
        return SessionResponse(
            auth=mode,
            user=None,
            needs_setup=False,
            signup_allowed=False,
            email_enabled=False,
            claude_key_available=False,
            claude_key=None,
            features=_features(),
        )
    token = bearer_token(authorization)
    user = auth.user_for_token(token) if token else None
    return SessionResponse(
        auth=mode,
        user=UserResponse(**auth.public_user(user)) if user else None,
        needs_setup=db.count_users() == 0,
        signup_allowed=auth.signup_allowed(),
        email_enabled=auth.email_enabled(),
        claude_key_available=claude_key.available(),
        claude_key=claude_key.status(user["id"]) if user and claude_key.available() else None,
        features=_features(),
    )


@router.post("/setup", response_model=TokenResponse, dependencies=[Depends(_require_accounts), Depends(_rate_limit_login)])
def first_run_setup(req: CredentialsRequest) -> TokenResponse:
    """Create the first account, as admin. Refused once any account exists."""
    try:
        return _signed_in(auth.create_first_admin(req.email, req.password))
    except auth.AuthError as exc:
        raise _auth_error(exc) from exc


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(_require_accounts), Depends(_rate_limit_login)])
def login(req: CredentialsRequest) -> TokenResponse:
    try:
        with login_throttle.attempt(req.email):
            user = auth.authenticate(req.email, req.password)
    except auth.AuthError as exc:
        raise _auth_error(exc) from exc
    return _signed_in(user)


@router.post(
    "/signup",
    response_model=TokenResponse | SignupPendingResponse,
    dependencies=[Depends(_require_accounts), Depends(_rate_limit_login)],
)
def signup(req: CredentialsRequest, response: Response, background: BackgroundTasks) -> TokenResponse | SignupPendingResponse:
    """Create an account and sign in; with email set up, email a link to finish instead, and answer
    the same whether or not the address has an account (docs/SECURITY_MODEL.md)."""
    # On a server with no account yet, signing up is the first-run setup: that account is the admin.
    if db.count_users() == 0:
        try:
            return _signed_in(auth.create_first_admin(req.email, req.password))
        except auth.AuthError as exc:
            if exc.status_code != 409:  # 409: someone else just became the admin; sign up normally.
                raise _auth_error(exc) from exc
    if not auth.signup_allowed():
        raise HTTPException(status_code=403, detail="Ask an admin of this server for an account")
    if auth.email_enabled():
        try:
            email = auth.check_signup(req.email, req.password)
        except auth.AuthError as exc:
            raise _auth_error(exc) from exc
        background.add_task(auth.send_signup_email, email, req.password)
        response.status_code = 202
        return SignupPendingResponse()
    # Without email, a taken address is refused (409), which tells that it has an account.
    try:
        return _signed_in(auth.create_user(req.email, req.password))
    except auth.AuthError as exc:
        raise _auth_error(exc) from exc


@router.post("/confirm-signup", response_model=TokenResponse, dependencies=[Depends(_require_accounts), Depends(_rate_limit_login)])
def confirm_signup(req: ConfirmSignupRequest) -> TokenResponse:
    """Finish signing up from the emailed link, and sign in."""
    if not auth.signup_allowed():
        raise HTTPException(status_code=403, detail="Ask an admin of this server for an account")
    try:
        return _signed_in(auth.confirm_signup(req.token))
    except auth.AuthError as exc:
        raise _auth_error(exc) from exc


class ResetRequest(BaseModel):
    token: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    # Revoke the account's API tokens too: the Account page asks, yes by default.
    revoke_tokens: bool = True


class SignedOutEverywhereResponse(BaseModel):
    tokens_revoked: int


@router.post("/reset", response_model=TokenResponse, dependencies=[Depends(_require_accounts), Depends(_rate_limit_login)])
def reset_password(req: ResetRequest) -> TokenResponse:
    """Set a new password from a one-time reset link, and sign in."""
    try:
        return _signed_in(auth.reset_password(req.token, req.password))
    except auth.AuthError as exc:
        raise _auth_error(exc) from exc


@router.post("/forgot", status_code=202, dependencies=[Depends(_require_accounts), Depends(_rate_limit_login)])
def forgot_password(req: ForgotPasswordRequest, background: BackgroundTasks) -> dict[str, bool]:
    """Email a reset link if the address has an active account. The answer is the same either way,
    and the email is sent after responding, so neither the reply nor its timing tells who has one."""
    background.add_task(auth.request_password_reset, req.email)
    return {"accepted": True}


@router.post("/password", status_code=204, dependencies=[Depends(_require_accounts), Depends(_rate_limit_login)])
def change_password(req: ChangePasswordRequest, viewer: CurrentViewer, authorization: str | None = Header(default=None)) -> None:
    try:
        auth.change_password(
            viewer.user_id,
            req.current_password,
            req.new_password,
            current_token=bearer_token(authorization),
            revoke_tokens=req.revoke_tokens,
        )
    except auth.AuthError as exc:
        raise _auth_error(exc) from exc


@router.post("/sign-out-everywhere", response_model=SignedOutEverywhereResponse, dependencies=[Depends(_require_accounts)])
def sign_out_everywhere(viewer: CurrentViewer, authorization: str | None = Header(default=None)) -> SignedOutEverywhereResponse:
    """End every other session of the signed-in user, and revoke their API tokens: after an account
    was taken over, nothing its intruder holds still works. This session stays."""
    return SignedOutEverywhereResponse(tokens_revoked=auth.sign_out_everywhere(viewer.user, current_token=bearer_token(authorization)))


# Signing in, and up, with GitHub (app/auth/github_sign_in.py). The web app holds the nonce cookie,
# and calls these from its own /api/auth/github routes.


class GitHubSignInStart(BaseModel):
    nonce_hash: str = Field(min_length=64, max_length=64)


class GitHubSignInUrl(BaseModel):
    url: str


class GitHubCallbackRequest(BaseModel):
    code: str = Field(min_length=1, max_length=512)
    state: str = Field(min_length=1, max_length=4096)
    # The nonce from the web app's cookie: only the browser that started can finish.
    nonce: str = Field(default="", max_length=512)


class GitHubCallbackResponse(BaseModel):
    outcome: Literal["signed_in", "signed_up", "linked"]
    # A new session, when the user was signed in or up.
    token: str | None = None
    expires_at: float | None = None
    user: UserResponse | None = None


def _require_github() -> None:
    if not github_sign_in.available():
        raise HTTPException(status_code=404, detail="Signing in with GitHub isn't set up on this server")


@router.post(
    "/github/start",
    response_model=GitHubSignInUrl,
    dependencies=[Depends(_require_accounts), Depends(_require_github), Depends(_rate_limit_login)],
)
def start_github_sign_in(req: GitHubSignInStart) -> GitHubSignInUrl:
    """GitHub's page to authorize signing in, or up, with it."""
    return GitHubSignInUrl(url=github_sign_in.start_url(intent="sign_in", nonce_hash=req.nonce_hash))


@router.post(
    "/github/callback",
    response_model=GitHubCallbackResponse,
    dependencies=[Depends(_require_accounts), Depends(_require_github), Depends(_rate_limit_login)],
)
def complete_github_sign_in(req: GitHubCallbackRequest, authorization: str | None = Header(default=None)) -> GitHubCallbackResponse:
    """GitHub's callback: sign in or up, with a session rotated like a password sign-in's, or link
    GitHub to the signed-in user's account."""
    token = bearer_token(authorization)
    viewer = auth.user_for_token(token) if token else None
    try:
        outcome, user = github_sign_in.complete(code=req.code, state=req.state, nonce=req.nonce, viewer=viewer)
    except auth.AuthError as exc:
        raise _auth_error(exc) from exc
    if outcome == "linked":
        return GitHubCallbackResponse(outcome=outcome)
    session = _signed_in(user)
    return GitHubCallbackResponse(outcome=outcome, token=session.token, expires_at=session.expires_at, user=session.user)


@router.post("/logout", status_code=204)
def logout(authorization: str | None = Header(default=None)) -> None:
    token = bearer_token(authorization)
    if token and auth.auth_mode() == "accounts":
        auth.end_session(token)
