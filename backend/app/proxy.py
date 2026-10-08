"""What the API knows about the web app in front of it (server/utils/backend.ts).

The web app is the API's only caller. With INSKECT_PROXY_SECRET set, every request must
carry it, so nothing else can reach the API, the per-IP limits included: for an API reachable other
than through the web app. The web app passes on the visitor's address in X-Inskect-Client-IP,
which proxies on the way (some rewrite X-Forwarded-For) leave alone.

It also says when it sees X-Forwarded-For without NUXT_TRUST_PROXY: behind a proxy that way, every
visitor seems to come from the proxy and shares one rate-limit bucket. The backoffice shows it.
"""

from __future__ import annotations

import hmac
import logging
import time

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings

SECRET_HEADER = "x-inskect-proxy-secret"
CLIENT_IP_HEADER = "x-inskect-client-ip"
UNTRUSTED_HEADER = "x-inskect-untrusted-forwarded-for"

# Shown for a day after the web app last said so.
_WARNING_SECONDS = 24 * 3600
_untrusted_seen_at: float | None = None
logger = logging.getLogger(__name__)


def is_from_web_app(request: Request) -> bool:
    secret = get_settings().proxy_secret
    if not secret:
        return True
    return hmac.compare_digest(request.headers.get(SECRET_HEADER, "").encode(), secret.encode())


async def check_caller(request: Request, call_next):
    """HTTP middleware: refuse callers without the proxy secret, and note the web app's warning."""
    if not is_from_web_app(request):
        return JSONResponse(status_code=403, content={"detail": "This API answers only its web app"})
    if request.headers.get(UNTRUSTED_HEADER):
        note_untrusted_forwarding()
    return await call_next(request)


def note_untrusted_forwarding() -> None:
    global _untrusted_seen_at
    if _untrusted_seen_at is None:
        logger.warning(
            "Requests reach the web app with X-Forwarded-For, but NUXT_TRUST_PROXY is off: behind a "
            "reverse proxy, every visitor shares the proxy's rate limits. Set NUXT_TRUST_PROXY=true "
            "on the web app (docs/REVERSE_PROXY.md)."
        )
    _untrusted_seen_at = time.time()


def warning() -> str | None:
    """The backoffice's warning about the proxy in front, if any."""
    if _untrusted_seen_at is None or time.time() - _untrusted_seen_at > _WARNING_SECONDS:
        return None
    return (
        "Requests reach the web app through a proxy (they carry X-Forwarded-For), but NUXT_TRUST_PROXY "
        "is off: every visitor seems to come from the proxy, and they all share one set of rate limits. "
        "Set NUXT_TRUST_PROXY=true on the web app."
    )


def reset() -> None:
    """Forget the warning (for tests)."""
    global _untrusted_seen_at
    _untrusted_seen_at = None
