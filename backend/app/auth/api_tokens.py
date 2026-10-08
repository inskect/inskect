"""Personal API tokens: scripts and CI jobs start and read scans as the user who made the token.

A user creates, names and revokes their tokens on the account page; an admin can revoke anyone's.
A token is shown once, when it's created: like a session, only its hash is stored, so neither the
API nor a leaked database can give it back. Its first characters (the prefix) are kept to tell a
user's tokens apart.

A token works as its owner: the same scans, quotas and rate limits, and it stops working when the
owner is suspended or deleted. Its scopes say what it may do; `scan` (start scans, and read,
export and rescan them) is the only one so far, and every other part of the API needs a browser
session. Creation and revocation are in the activity log, and so is a token's first use each day,
which keeps the log readable however often a script runs.
"""

from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from typing import Any, Literal

from app import db
from app.auth import AuthError, audit

# Tells a token from a session token, and from other services' tokens in a leaked file.
TOKEN_PREFIX = "sst_"
Scope = Literal["scan"]
SCOPES: tuple[Scope, ...] = ("scan",)
MAX_TOKENS_PER_USER = 20
MAX_NAME_LENGTH = 80
# last_used_at is updated at most this often, so a busy script doesn't write on every request.
LAST_USED_RESOLUTION = 60.0


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def is_api_token(token: str) -> bool:
    return token.startswith(TOKEN_PREFIX)


def public_token(row: dict[str, Any]) -> dict[str, Any]:
    """A token as listed: never its value or hash."""
    return {
        "id": row["id"],
        "name": row["name"],
        "prefix": row["prefix"],
        "scopes": row["scopes"].split(),
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "last_used_at": row["last_used_at"],
    }


def create(user: dict[str, Any], *, name: str, expires_in_days: int | None, scopes: tuple[Scope, ...] = SCOPES) -> tuple[str, dict[str, Any]]:
    """A new token for user: its value, to show once, and how it's listed."""
    name = " ".join(name.split())
    if not name:
        raise AuthError("Give the token a name, to tell it apart later")
    if len(name) > MAX_NAME_LENGTH:
        raise AuthError(f"Use at most {MAX_NAME_LENGTH} characters for the name")
    if len(db.list_api_tokens(user["id"])) >= MAX_TOKENS_PER_USER:
        raise AuthError(f"You have {MAX_TOKENS_PER_USER} tokens already: revoke one you no longer use first")
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    now = time.time()
    row = {
        "id": uuid.uuid4().hex,
        "user_id": user["id"],
        "name": name,
        "prefix": token[: len(TOKEN_PREFIX) + 6],
        "scopes": " ".join(scopes),
        "created_at": now,
        "expires_at": now + expires_in_days * 86400 if expires_in_days else None,
    }
    db.create_api_token(token_hash=_hash(token), **row)
    audit(user, "token.created", user, name)
    return token, public_token({**row, "last_used_at": None})


def authenticate(token: str) -> tuple[dict[str, Any], frozenset[str]] | None:
    """The user a valid token belongs to, and its scopes; None for a revoked, expired or unknown one."""
    found = db.get_api_token_user(_hash(token), now=time.time())
    if found is None:
        return None
    now = time.time()
    last_used = found.pop("token_last_used_at")
    token_id, token_name, scopes = found.pop("token_id"), found.pop("token_name"), found.pop("token_scopes")
    if last_used is None or now - last_used >= LAST_USED_RESOLUTION:
        db.mark_api_token_used(token_id, now)
    # Its first use each day (UTC) goes in the activity log.
    if last_used is None or time.gmtime(last_used)[:3] != time.gmtime(now)[:3]:
        audit(found, "token.used", found, token_name)
    return found, frozenset(scopes.split())


def revoke(actor: dict[str, Any] | None, owner: dict[str, Any], token_id: str) -> None:
    """Revoke one of owner's tokens: it stops working at once."""
    revoked = db.delete_api_token(token_id, user_id=owner["id"])
    if revoked is None:
        raise AuthError("No such token", status_code=404)
    audit(actor, "token.revoked", owner, revoked["name"])
