"""Request rate limits.

INSKECT_RATE_LIMIT_STORE picks where hits are counted: `memory` (this process only, the
default with SQLite) or `database` (the scan database, shared by every process using it, the default
with Postgres).
"""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict, deque
from typing import TYPE_CHECKING, Literal, Protocol

from fastapi import HTTPException, Request

from app import db
from app.core.config import Settings, get_settings

if TYPE_CHECKING:
    from app.auth import Viewer

RateLimitStoreKind = Literal["memory", "database"]

_MAX_TRACKED_CLIENTS = 1000


class RateLimitStore(Protocol):
    def hit(self, key: str, limit: int, window_seconds: float) -> float | None:
        """Record a hit for key if it's within the rate. Returns None when it is, otherwise how
        many seconds until the next hit would be allowed (the refused hit isn't recorded)."""

    def forget(self, key: str) -> None:
        """Drop key's most recent hit: what it counted turned out not to count."""


class MemoryRateLimitStore:
    """Sliding windows in this process's memory, for the most recently seen clients."""

    def __init__(self) -> None:
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: float) -> float | None:
        now = time.monotonic()
        with self._lock:
            window = self._hits.get(key)
            if window is None:
                window = deque()
                self._hits[key] = window
                while len(self._hits) > _MAX_TRACKED_CLIENTS:
                    self._hits.popitem(last=False)
            else:
                self._hits.move_to_end(key)

            cutoff = now - window_seconds
            while window and window[0] <= cutoff:
                window.popleft()

            if len(window) >= limit:
                return window[-limit] + window_seconds - now
            window.append(now)
            return None

    def forget(self, key: str) -> None:
        with self._lock:
            window = self._hits.get(key)
            if window:
                window.pop()


class DatabaseRateLimitStore:
    """Sliding windows in the scan database, so every instance counts the same hits."""

    def hit(self, key: str, limit: int, window_seconds: float) -> float | None:
        return db.rate_limit_hit(key, limit=limit, window_seconds=window_seconds, now=time.time())

    def forget(self, key: str) -> None:
        db.rate_limit_forget(key)


def rate_limit_store_kind(settings: Settings) -> RateLimitStoreKind:
    """INSKECT_RATE_LIMIT_STORE when set, otherwise the database with Postgres."""
    if settings.rate_limit_store:
        return settings.rate_limit_store
    return "database" if settings.database_url else "memory"


def create_rate_limit_store(settings: Settings) -> RateLimitStore:
    return DatabaseRateLimitStore() if rate_limit_store_kind(settings) == "database" else MemoryRateLimitStore()


_store: RateLimitStore | None = None
_store_lock = threading.Lock()


def _get_store() -> RateLimitStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = create_rate_limit_store(get_settings())
    return _store


def reset() -> None:
    """Forget every hit counted in memory, and pick the store again from the settings (for tests)."""
    global _store
    with _store_lock:
        _store = None


def hit(key: str, limit: int, window_seconds: float) -> float | None:
    """Record a hit for key; None when it's within the rate, otherwise seconds until retry."""
    return _get_store().hit(key, limit, window_seconds)


def forget(key: str) -> None:
    """Drop key's most recent hit, for a request that turned out not to count."""
    _get_store().forget(key)


def enforce(key: str, limit: int, window_seconds: float, message: str) -> None:
    """Record a hit for key, or refuse the request with a 429 that says when to retry."""
    retry_after = hit(key, limit, window_seconds)
    if retry_after is not None:
        refuse(retry_after, message)


def refuse(retry_after: float, message: str) -> None:
    """A 429 that says when to retry."""
    seconds = max(1, math.ceil(retry_after))
    raise HTTPException(
        status_code=429,
        detail=f"{message} — try again in {_duration(seconds)}",
        headers={"Retry-After": str(seconds)},
    )


def _duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    if seconds < 3600:
        minutes = math.ceil(seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours = math.ceil(seconds / 3600)
    return f"{hours} hour{'s' if hours != 1 else ''}"


def client_key(request: Request) -> str:
    """The visitor's address, as the web app passed it on (app/proxy.py); X-Forwarded-For for other
    callers of a private API (tests, scripts on the server), then the socket's."""
    from app.proxy import CLIENT_IP_HEADER

    passed_on = request.headers.get(CLIENT_IP_HEADER)
    if passed_on:
        return passed_on.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def subject_key(request: Request, viewer: Viewer) -> str:
    """Who a limit applies to: the signed-in user, or the client address for anyone else."""
    if viewer.user_id:
        return f"user:{viewer.user_id}"
    return f"ip:{client_key(request)}"
