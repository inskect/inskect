"""Each user's own Claude (Anthropic) API key, saved encrypted to their account.

Users connect a key from their account page; it's checked with Anthropic, encrypted with
app/secrets_box.py and only ever shown back as a hint (…a1b2). Their AI scans then use it, without
pasting it each time.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app import auth, db, secrets_box
from app.auth import AuthError

PROVIDER = "anthropic"
_KEY_PREFIX = "sk-ant-"
_ANTHROPIC_MODELS_URL = "https://api.anthropic.com/v1/models"
_VERIFY_TIMEOUT_SECONDS = 10


def available() -> bool:
    """Saving a key needs accounts (someone to own it) and a secret key to encrypt it with."""
    return auth.auth_mode() == "accounts" and secrets_box.is_configured()


def _context(user_id: str) -> str:
    return f"llm-credential:{user_id}"


def hint(key: str) -> str:
    return f"…{key[-4:]}"


def verify_with_anthropic(key: str) -> None:
    """Ask Anthropic whether the key works, without spending tokens (it lists models)."""
    try:
        response = httpx.get(
            _ANTHROPIC_MODELS_URL,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            timeout=_VERIFY_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise AuthError("Couldn't reach Anthropic to check the key; try again in a moment", 502) from exc
    if response.status_code in (401, 403):
        raise AuthError("Anthropic didn't accept this key. Check it on console.anthropic.com", 400)
    if response.status_code >= 400:
        raise AuthError("Anthropic couldn't check the key right now; try again in a moment", 502)


def status(user_id: str) -> dict[str, Any] | None:
    credential = db.get_llm_credential(user_id)
    if credential is None:
        return None
    return {"provider": credential["provider"], "hint": credential["key_hint"], "updated_at": credential["updated_at"]}


def connect(user: dict[str, Any], key: str) -> dict[str, Any]:
    if not available():
        raise AuthError("Saving a Claude key isn't available on this server", 404)
    key = key.strip()
    if not key.startswith(_KEY_PREFIX) or len(key) < 20 or any(c.isspace() for c in key):
        raise AuthError("That doesn't look like an Anthropic API key (they start with sk-ant-)", 400)
    verify_with_anthropic(key)
    replaced = db.get_llm_credential(user["id"]) is not None
    db.set_llm_credential(
        user_id=user["id"],
        provider=PROVIDER,
        encrypted_key=secrets_box.encrypt(key, context=_context(user["id"])),
        key_hint=hint(key),
        now=time.time(),
    )
    auth.audit(user, "account.claude_connected", user, f"replaced, now {hint(key)}" if replaced else hint(key))
    return status(user["id"])


def disconnect(user: dict[str, Any]) -> None:
    if db.delete_llm_credential(user["id"]):
        auth.audit(user, "account.claude_disconnected", user)


def saved_key(user_id: str) -> str | None:
    """The user's decrypted key, for the scan about to use it. Never returned by the API."""
    credential = db.get_llm_credential(user_id)
    if credential is None:
        return None
    return secrets_box.decrypt(credential["encrypted_key"], context=_context(user_id))


def _scan_context(scan_id: str) -> str:
    return f"scan-secret:{scan_id}"


def hold_for_scan(scan_id: str, key: str) -> None:
    """Keep a one-off key, encrypted, until its queued scan has run."""
    db.put_scan_secret(scan_id=scan_id, encrypted_key=secrets_box.encrypt(key, context=_scan_context(scan_id)), now=time.time())


def held_for_scan(scan_id: str) -> str | None:
    encrypted = db.get_scan_secret(scan_id)
    return secrets_box.decrypt(encrypted, context=_scan_context(scan_id)) if encrypted else None


def hold_llm_for_scan(scan_id: str, *, api_key: str | None, base_url: str | None) -> None:
    """Keep a scan's one-off AI credentials, any provider's key and endpoint, encrypted until it has
    run: a self-hosted API that restarts mid-scan runs it again with them (app/jobs/in_process.py)."""
    hold_for_scan(scan_id, json.dumps({"api_key": api_key, "base_url": base_url}))


def held_llm_for_scan(scan_id: str) -> dict[str, str | None] | None:
    """What hold_llm_for_scan kept, or a key hold_for_scan did, as {api_key, base_url}."""
    held = held_for_scan(scan_id)
    if held is None:
        return None
    try:
        parsed = json.loads(held)
    except ValueError:
        return {"api_key": held, "base_url": None}
    return parsed if isinstance(parsed, dict) else {"api_key": held, "base_url": None}
