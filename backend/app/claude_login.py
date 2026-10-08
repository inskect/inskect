from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass

from app.core.config import get_settings

_START_READ_SECONDS = 15.0
_COMPLETE_TIMEOUT_SECONDS = 30.0
_STALE_PENDING_SECONDS = 300.0
_URL_RE = re.compile(r"https://\S+")
_AUTH_STATUS_TIMEOUT_SECONDS = 15.0
# How long the login's status is trusted: checking starts the CLI, which costs hundreds of
# milliseconds and tens of MB, and health (every home page view) and the history ask for it.
_STATUS_TTL_SECONDS = 60.0


@dataclass
class PendingLogin:
    process: asyncio.subprocess.Process
    started_at: float


_pending: PendingLogin | None = None
_lock = asyncio.Lock()


def _env_without_api_key() -> dict[str, str]:
    # main.py sets a placeholder ANTHROPIC_API_KEY, and scans may set a user's real one; either
    # would make the CLI report API-key auth instead of its own login.
    return {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}


# (when it was checked, on time.monotonic(); whether it was logged in)
_status: tuple[float, bool] | None = None
# Bumped when the login changes, so a check that began before then isn't kept.
_generation = 0
# Held while checking, so requests arriving meanwhile wait for that check instead of each starting one.
_status_lock = threading.Lock()


def claude_cli_enabled() -> bool:
    """Whether scans may use the server's Claude Code login: allowed here (INSKECT_CLAUDE_CLI),
    and signed in."""
    return get_settings().claude_cli and is_claude_cli_available()


def is_claude_cli_available() -> bool:
    """Whether the server's `claude` CLI is logged in, as checked within the last minute. Signing
    in from the backoffice checks again straight away (forget_cli_status)."""
    global _status
    with _status_lock:
        if _status is not None and time.monotonic() - _status[0] < _STATUS_TTL_SECONDS:
            return _status[1]
        generation = _generation
        available = _check_cli()
        if generation == _generation:
            _status = (time.monotonic(), available)
        return available


def forget_cli_status() -> None:
    """Check the login again on the next ask: it was just changed. Without the lock, so the event
    loop never waits on a check in progress."""
    global _status, _generation
    _generation += 1
    _status = None


def _check_cli() -> bool:
    """Whether the server's `claude` CLI is logged in, without touching os.environ."""
    binary = shutil.which("claude")
    if binary is None:
        return False
    try:
        result = subprocess.run(
            [binary, "auth", "status"],
            capture_output=True,
            check=False,
            env=_env_without_api_key(),
            timeout=_AUTH_STATUS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    out = result.stdout.decode(errors="replace").strip()
    try:
        logged_in = bool(json.loads(out).get("loggedIn"))
    except (json.JSONDecodeError, AttributeError):
        logged_in = result.returncode == 0 and "not logged in" not in out.lower()
    return result.returncode == 0 and logged_in


async def start_claude_login() -> str:
    global _pending
    async with _lock:
        if _pending is not None:
            if time.time() - _pending.started_at < _STALE_PENDING_SECONDS:
                raise RuntimeError("A login is already in progress")
            _pending.process.kill()
            _pending = None

        env = _env_without_api_key()
        process = await asyncio.create_subprocess_exec(
            "claude",
            "auth",
            "login",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )

        buffer = b""
        deadline = time.monotonic() + _START_READ_SECONDS
        while time.monotonic() < deadline:
            try:
                chunk = await asyncio.wait_for(process.stdout.read(256), timeout=1)
            except TimeoutError:
                continue
            if not chunk:
                break
            buffer += chunk
            if b"Paste code here" in buffer:
                break

        match = _URL_RE.search(buffer.decode(errors="replace"))
        if not match:
            process.kill()
            raise RuntimeError("Could not find a login URL in the CLI's output")

        _pending = PendingLogin(process=process, started_at=time.time())
        return match.group(0)


async def complete_claude_login(code: str) -> tuple[bool, str]:
    global _pending
    async with _lock:
        if _pending is None:
            raise RuntimeError("No login is in progress")
        process = _pending.process
        try:
            stdout, _ = await asyncio.wait_for(
                process.communicate(input=(code.strip() + "\n").encode()),
                timeout=_COMPLETE_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            process.kill()
            _pending = None
            raise RuntimeError("Login did not complete in time") from None

        success = process.returncode == 0
        _pending = None
        forget_cli_status()
        return success, stdout.decode(errors="replace")


def kill_pending() -> None:
    global _pending
    if _pending is not None:
        _pending.process.kill()
        _pending = None
