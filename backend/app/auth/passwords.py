"""Password hashing with the standard library's scrypt, so accounts need no extra dependency."""

from __future__ import annotations

import base64
import functools
import hashlib
import hmac
import secrets

# One of OWASP's equivalent minimums for scrypt (N=2^15, r=8, p=3): 32 MiB per hash, which suits
# a small home server and serverless functions better than the 128 MiB N=2^17 variant.
_N, _R, _P = 2**15, 8, 3
_MAXMEM = 64 * 1024 * 1024
_KEY_LENGTH = 32

MIN_PASSWORD_LENGTH = 10


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, maxmem=_MAXMEM, dklen=_KEY_LENGTH)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, _N, _R, _P)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str | None) -> bool:
    """Whether the password matches. An account without one (made with GitHub) matches none, after
    as long a check as any other, so the time it takes doesn't tell."""
    if not encoded:
        verify_password(password, dummy_hash())
        return False
    try:
        scheme, n, r, p, salt, digest = encoded.split("$")
        if scheme != "scrypt":
            return False
        actual = _scrypt(password, base64.b64decode(salt), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, base64.b64decode(digest))


@functools.cache
def dummy_hash() -> str:
    """Checked against when the email is unknown, so a login takes as long whether or not it exists."""
    return hash_password(secrets.token_urlsafe(16))
