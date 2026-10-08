"""Signing in, and up, with GitHub, through the server's GitHub App: the one users connect to scan
private repositories (app/repo_connections.py), with the "Email addresses: read" account permission.

- A GitHub account is known by its numeric user ID, never its login, which its owner can change.
- Signing in grants no access to repositories. GitHub's token is used to read who the user is and
  their verified emails, then revoked; connecting repositories stays a step of its own.
- The state GitHub sends back is encrypted, lasts 10 minutes, is redeemed once, and carries the
  hash of a nonce the web app keeps in an httpOnly cookie: only the browser that started can finish
  (against cross-site requests and login fixation).
- A GitHub account is never linked to an account here because their emails match: whoever controls
  an email on GitHub would take the account over. Its owner links GitHub from their Account page.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlencode

import httpx

from app import db, mail, rate_limit, repo_connections, secrets_box
from app.auth import AuthError, audit, normalize_email, signup_allowed, verify_password
from app.core.config import get_settings

PROVIDER = "github"
CALLBACK_PATH = "/api/auth/github/callback"
_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_API = "https://api.github.com"
STATE_SECONDS = 600
# For an account without a password, what a password re-asked would confirm: a sign-in this recent.
RECENT_SIGN_IN_SECONDS = 600

Intent = Literal["sign_in", "link"]
Outcome = Literal["signed_in", "signed_up", "linked"]

SUSPENDED = "This account is suspended. Contact an admin of this server."


def available() -> bool:
    """With the GitHub App set up, as for connecting repositories: nothing more to configure."""
    return repo_connections.available()


def nonce_hash(nonce: str) -> str:
    return hashlib.sha256(nonce.encode()).hexdigest()


_STATE_CONTEXT = "github-sign-in-state"


def start_url(*, intent: Intent, nonce_hash: str, user_id: str | None = None) -> str:
    """GitHub's authorization page, with a state only the browser holding the nonce can redeem."""
    settings = get_settings()
    payload = {
        "id": secrets.token_urlsafe(16),
        "intent": intent,
        "nonce_hash": nonce_hash,
        "user_id": user_id,
        "expires_at": time.time() + STATE_SECONDS,
    }
    state = secrets_box.encrypt(json.dumps(payload), context=_STATE_CONTEXT)
    query = {"client_id": settings.github_app_client_id, "redirect_uri": mail.public_link(CALLBACK_PATH), "state": state}
    return f"{_AUTHORIZE_URL}?{urlencode(query)}"


def _redeem_state(state: str, nonce: str | None) -> dict[str, Any]:
    try:
        payload = json.loads(secrets_box.decrypt(state, context=_STATE_CONTEXT))
    except Exception as exc:
        raise AuthError("That GitHub sign-in isn't valid: start again", 400) from exc
    if payload.get("expires_at", 0) < time.time():
        raise AuthError("That GitHub sign-in took too long: start again", 400)
    if not nonce or not hmac.compare_digest(nonce_hash(nonce), str(payload.get("nonce_hash"))):
        raise AuthError("That GitHub sign-in was started in another browser: start again here", 400)
    # Once: a state seen before is refused, wherever it comes from.
    if rate_limit.hit(f"github-state:{payload['id']}", 1, STATE_SECONDS) is not None:
        raise AuthError("That GitHub sign-in was used already: start again", 400)
    return payload


@dataclass(frozen=True)
class Identity:
    github_id: str
    login: str
    # The verified primary email, if the account has one and lets the app read it.
    email: str | None


def _api_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def _revoke(token: str) -> None:
    """Revoke this one token (not the app's grant, which a repository connection may use)."""
    settings = get_settings()
    try:
        with repo_connections._http() as client:
            client.request(
                "DELETE",
                f"{_API}/applications/{settings.github_app_client_id}/token",
                auth=(settings.github_app_client_id or "", settings.github_app_client_secret or ""),
                json={"access_token": token},
                headers={"Accept": "application/vnd.github+json"},
            )
    except httpx.HTTPError:
        pass  # It lapses at GitHub anyway, and it was never stored.


def _identity(code: str) -> Identity:
    """Who signed in on GitHub, from the code it sent back. The token it gives is revoked after."""
    data = repo_connections._exchange({"code": code, "redirect_uri": mail.public_link(CALLBACK_PATH)})
    token = data.get("access_token")
    if not token:
        raise AuthError(f"GitHub refused the sign-in: {data.get('error_description') or data.get('error') or 'no token'}", 400)
    try:
        with repo_connections._http() as client:
            user = client.get(f"{_API}/user", headers=_api_headers(token))
            emails = client.get(f"{_API}/user/emails", headers=_api_headers(token))
    except httpx.HTTPError as exc:
        raise AuthError("GitHub didn't answer: try again in a moment", 502) from exc
    finally:
        _revoke(token)
    if user.status_code != 200 or "id" not in user.json():
        raise AuthError("GitHub didn't say who you are: try again", 502)
    profile = user.json()
    email = None
    if emails.status_code == 200:
        email = next((entry["email"] for entry in emails.json() if entry.get("primary") and entry.get("verified")), None)
    return Identity(str(profile["id"]), str(profile.get("login") or ""), email)


def complete(*, code: str, state: str, nonce: str | None, viewer: dict[str, Any] | None) -> tuple[Outcome, dict[str, Any]]:
    """Redeem GitHub's callback: sign in the linked account, sign up a new one, or link GitHub to
    the signed-in user's, as the sign-in started."""
    payload = _redeem_state(state, nonce)
    identity = _identity(code)
    if payload["intent"] == "link":
        if viewer is None or viewer["id"] != payload.get("user_id"):
            raise AuthError("Sign in as the account you were linking GitHub to, then link it again", 403)
        return "linked", link(viewer, identity)

    user = db.get_identity_user(PROVIDER, identity.github_id)
    if user is not None:
        if user["status"] != "active":
            raise AuthError(SUSPENDED, 403)
        # The login only labels it on the Account page; the ID is what signs in.
        db.rename_identity(PROVIDER, identity.github_id, identity.login)
        return "signed_in", user
    return "signed_up", _sign_up(identity)


def _sign_up(identity: Identity) -> dict[str, Any]:
    if db.count_users() == 0:
        raise AuthError("Create this server’s first admin with an email and a password", 409)
    if not signup_allowed():
        raise AuthError("Ask an admin of this server for an account", 403)
    if not identity.email:
        raise AuthError("Your GitHub account has no verified primary email that the app can read: verify one on GitHub, or sign up with an email", 400)
    email = normalize_email(identity.email)
    if db.get_user_by_email(email):
        raise AuthError("An account already uses this email: sign in with its password, then link GitHub from your Account page", 409)
    fields = {"id": uuid.uuid4().hex, "email": email, "password_hash": None, "role": "user", "created_at": time.time()}
    db.create_user(**fields)
    db.add_identity(provider=PROVIDER, provider_user_id=identity.github_id, user_id=fields["id"], display_name=identity.login, created_at=time.time())
    audit(fields, "account.created", fields, "signed up with GitHub")
    return {**fields, "status": "active"}


def link(user: dict[str, Any], identity: Identity) -> dict[str, Any]:
    owner = db.get_identity_user(PROVIDER, identity.github_id)
    if owner is not None and owner["id"] != user["id"]:
        raise AuthError("This GitHub account already signs in to another account here", 409)
    if owner is None:
        if any(row["provider"] == PROVIDER for row in db.list_identities(user["id"])):
            raise AuthError("Another GitHub account is linked already: unlink it first", 409)
        db.add_identity(provider=PROVIDER, provider_user_id=identity.github_id, user_id=user["id"], display_name=identity.login, created_at=time.time())
        audit(user, "auth.github_linked", user, f"GitHub @{identity.login}")
    return user


def unlink(user: dict[str, Any]) -> bool:
    """Stop GitHub signing in to the account; never its last way in."""
    linked = next((row for row in db.list_identities(user["id"]) if row["provider"] == PROVIDER), None)
    if linked is None:
        return False
    full = db.get_user(user["id"]) or {}
    if not full.get("password_hash"):
        raise AuthError("GitHub is how you sign in: set a password first, with “Forgot password?” on the sign-in page", 409)
    db.delete_identity(user["id"], PROVIDER)
    audit(user, "auth.github_unlinked", user, f"GitHub @{linked['display_name']}")
    return True


def methods(user_id: str) -> dict[str, Any]:
    """How the user can sign in, for their Account page."""
    user = db.get_user(user_id) or {}
    github = next((row for row in db.list_identities(user_id) if row["provider"] == PROVIDER), None)
    return {
        "password": bool(user.get("password_hash")),
        "github": {"login": github["display_name"], "linked_at": github["created_at"]} if github else None,
        "github_available": available(),
    }


def confirm_identity(user_id: str, password: str | None, *, session_token_hash: str | None) -> None:
    """Re-authentication, before what outlives the session (an API token, deleting the account):
    the password, or for an account without one, a sign-in in the last 10 minutes."""
    user = db.get_user(user_id) or {}
    if user.get("password_hash"):
        if not verify_password(password or "", user["password_hash"]):
            raise AuthError("Your password is wrong", 403)
        return
    started = db.get_session_created_at(session_token_hash) if session_token_hash else None
    if started is None or time.time() - started > RECENT_SIGN_IN_SECONDS:
        raise AuthError("Sign in with GitHub again, then do this within 10 minutes", 403)
