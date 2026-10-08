"""Share links (`/shared/<token>`): the read-only result anyone with the link can open.

A link is stored as its hash, as session and API tokens are, so a copy of the database (a backup,
a read-only leak) opens no shared result. With SECRET_KEY, the link is also kept encrypted, so its
owner can copy it again from the result page; without it, the link is shown once, when it's made,
and the owner can make a new one, which replaces it.

A status badge's report link doesn't need the link at all: `/shared/badge-<scan id>` opens the
scan on a target's badge, for as long as it's on it. It's public through its badge anyway.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from typing import Any

from app import db, secrets_box

BADGE_PREFIX = "badge-"
_CONTEXT = "share-token"
logger = logging.getLogger(__name__)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _secret(token: str) -> str | None:
    return secrets_box.encrypt(token, context=_CONTEXT) if secrets_box.is_configured() else None


def create(scan_id: str) -> str:
    """A new link to the scan's result, replacing any it had."""
    token = secrets.token_urlsafe(24)
    db.set_share_token(scan_id, token_hash(token), _secret(token))
    return token


def revoke(scan_id: str) -> None:
    db.set_share_token(scan_id, None)


def is_shared(scan: dict[str, Any]) -> bool:
    return bool(scan.get("share_token_hash"))


def stored_token(scan: dict[str, Any]) -> str | None:
    """The scan's link, when it's kept encrypted and the key is there to read it; otherwise None,
    and only whoever saved it when it was made has it."""
    secret = scan.get("share_token_secret")
    if not secret or not secrets_box.is_configured():
        return None
    try:
        return secrets_box.decrypt(secret, context=_CONTEXT)
    except secrets_box.SecretBoxError:
        return None


def badge_link(scan: dict[str, Any]) -> str:
    """What a badge's report link opens: the scan on the badge, by its id."""
    return f"{BADGE_PREFIX}{scan['id']}"


def find(token: str) -> dict[str, Any] | None:
    """The shared scan a link opens: by its hash, or a badge's (badge_link) while it's on the badge."""
    if token.startswith(BADGE_PREFIX):
        scan = db.get_scan(token.removeprefix(BADGE_PREFIX))
        return scan if scan and scan.get("badge") and is_shared(scan) else None
    return db.get_shared_scan(token_hash(token))


def hash_plain_tokens() -> int:
    """Hash the links stored as they were before (at startup): they keep working, and the database
    no longer holds them. With SECRET_KEY, their owners can still copy them."""
    plain = db.plain_share_tokens()
    for scan_id, token in plain:
        db.set_share_token(scan_id, token_hash(token), _secret(token))
    if plain:
        logger.info("Hashed %d share link(s) stored before links were hashed", len(plain))
    return len(plain)
