"""Failed sign-ins per account, wherever they come from.

The sign-in route also limits attempts per client address; this limit is keyed on the email, so
guesses spread over many addresses are slowed too. It applies to every email alike, whether or
not it has an account, so being refused doesn't tell which ones do.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from app import auth, db, monitoring, rate_limit

# Failed sign-ins allowed per account within each window, longest first: a few in 15 minutes,
# then fewer per hour and per day, so each lockout lasts longer than the one before.
# Also stated in monitoring.py's LOCKOUT_RULE and docs/SECURITY_MODEL.md.
TIERS = ((20, 24 * 3600), (10, 3600), (5, 15 * 60))


def _key(email: str, window_seconds: int) -> str:
    return f"login-account:{window_seconds}:{email}"


def _count(email: str) -> float | None:
    """Count an attempt in every window; None when each had room, otherwise seconds until the
    full one does (and the attempt isn't counted anywhere)."""
    counted = []
    for limit, window in TIERS:
        retry_after = rate_limit.hit(_key(email, window), limit, window)
        if retry_after is not None:
            for key in counted:
                rate_limit.forget(key)
            return retry_after
        counted.append(_key(email, window))
    return None


def _uncount(email: str) -> None:
    for _, window in TIERS:
        rate_limit.forget(_key(email, window))


def _report_lockout(email: str) -> None:
    """Once per lockout: a monitoring event (which alerts), and an entry in the account's activity."""
    if rate_limit.hit(f"login-locked:{email}", 1, TIERS[-1][1]) is not None:
        return
    monitoring.record(monitoring.SIGN_IN_LOCKED)
    user = db.get_user_by_email(email)
    if user is not None:
        auth.audit(None, "sign_in.locked", user, "too many failed sign-ins")


@contextmanager
def attempt(email: str) -> Iterator[None]:
    """Around checking a password: refuses the attempt (429) once the account has had too many
    failures. The attempt is counted before the password is checked, so concurrent guesses can't
    all slip through, and uncounted again unless it fails with a wrong password."""
    try:
        email = auth.normalize_email(email)
    except auth.AuthError:
        # No account has this email: nothing to protect, and the password check fails anyway.
        yield
        return
    retry_after = _count(email)
    if retry_after is not None:
        _report_lockout(email)
        rate_limit.refuse(retry_after, "Too many failed sign-ins with this email")
    try:
        yield
    except auth.AuthError as exc:
        if exc.status_code != 401:
            _uncount(email)
        raise
    except BaseException:
        _uncount(email)
        raise
    _uncount(email)
