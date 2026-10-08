"""Encryption at rest for stored API keys (AES-256-GCM under INSKECT_SECRET_KEY).

Each value is bound to a context string, such as the owning user's id, so a ciphertext copied into
another user's row doesn't decrypt. Generate a key with:

    uv run python -m app.secrets_box
"""

from __future__ import annotations

import base64
import binascii
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings, get_settings

_VERSION = "v1"


class SecretBoxError(Exception):
    """No usable secret key, or a value that can't be decrypted with it."""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def generate_key() -> str:
    return _b64(secrets.token_bytes(32))


def is_configured(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    try:
        _key(settings)
    except SecretBoxError:
        return False
    return True


def _key(settings: Settings) -> bytes:
    if not settings.secret_key:
        raise SecretBoxError("INSKECT_SECRET_KEY isn't set")
    try:
        key = _unb64(settings.secret_key.strip())
    except (binascii.Error, ValueError) as exc:
        raise SecretBoxError("INSKECT_SECRET_KEY isn't valid base64") from exc
    if len(key) != 32:
        raise SecretBoxError("INSKECT_SECRET_KEY must be 32 bytes (generate one with python -m app.secrets_box)")
    return key


def encrypt(plaintext: str, *, context: str, settings: Settings | None = None) -> str:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_key(settings or get_settings())).encrypt(nonce, plaintext.encode(), context.encode())
    return f"{_VERSION}:{_b64(nonce)}:{_b64(ciphertext)}"


def decrypt(token: str, *, context: str, settings: Settings | None = None) -> str:
    try:
        version, nonce, ciphertext = token.split(":")
        if version != _VERSION:
            raise ValueError(version)
        plaintext = AESGCM(_key(settings or get_settings())).decrypt(_unb64(nonce), _unb64(ciphertext), context.encode())
    except (ValueError, binascii.Error, InvalidTag) as exc:
        raise SecretBoxError("A stored secret couldn't be decrypted (was the secret key changed?)") from exc
    return plaintext.decode()


if __name__ == "__main__":
    print(generate_key())
