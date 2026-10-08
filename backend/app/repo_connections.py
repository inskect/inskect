"""Code host accounts users connect to scan their private repositories: GitHub, for now.

A user connects GitHub from their account page through the server's GitHub App (OAuth, the app's
"Contents: read" permission only), and chooses on GitHub which repositories it may read. Their user
access token, with its refresh token, is stored encrypted with SECRET_KEY, refreshed when it expires,
and deleted when they disconnect or their account is deleted. It reads only what both they and the
app's installation can: another user's connection never reaches it.

A scan of a GitHub link checks the repository with the owner's token when it's queued
(private_for): a public one is scanned as before, without the token; a private one is marked
`private_source` and scanned with it, fetched from the scan's owner when it runs (token_for), never
carried in the request, the queue or a log. The repository is cloned here, with the token in the
clone's own environment (local_copy), never this process's or a file, and the copy scanned.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlencode, urlsplit

import httpx

from app import auth, db, mail, secrets_box
from app.core.config import Settings, get_settings

GITHUB = "github"
_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_TOKEN_URL = "https://github.com/login/oauth/access_token"
_API = "https://api.github.com"
CALLBACK_PATH = "/api/account/connections/github/callback"
_STATE_SECONDS = 600
# Refreshed this long before it expires, so a scan never starts with a token about to lapse.
_REFRESH_MARGIN_SECONDS = 300
_HTTP_TIMEOUT_SECONDS = 10
_CLONE_TIMEOUT_SECONDS = 300
# skillspector's own ingest cap (INGEST_MAX_BYTES), for the copies made here.
MAX_COPY_BYTES = 100 * 1024 * 1024


class ConnectionFailedError(Exception):
    """A connection step that failed, with the reason to show."""


def _http() -> httpx.Client:
    """The client every call to GitHub goes through; tests swap in a transport."""
    return httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS, headers={"User-Agent": "inskect"})


def available(settings: Settings | None = None) -> bool:
    """Connecting GitHub needs accounts (someone to own it), SECRET_KEY, PUBLIC_URL for the
    callback, and the GitHub App's client ID and secret."""
    settings = settings or get_settings()
    return bool(
        auth.auth_mode() == "accounts"
        and secrets_box.is_configured(settings)
        and settings.public_url
        and settings.github_app_client_id
        and settings.github_app_client_secret
    )


def manage_url(settings: Settings | None = None) -> str | None:
    """Where a user chooses which repositories the app reads."""
    settings = settings or get_settings()
    return f"https://github.com/apps/{settings.github_app_slug}/installations/new" if settings.github_app_slug else None


# Connecting.


def _state_context(user_id: str) -> str:
    return f"repo-connection-state:{GITHUB}:{user_id}"


def start_url(user_id: str) -> str:
    """GitHub's authorization page, with a state only this user's callback can redeem, briefly."""
    settings = get_settings()
    payload = json.dumps({"nonce": secrets.token_urlsafe(16), "expires_at": time.time() + _STATE_SECONDS})
    state = secrets_box.encrypt(payload, context=_state_context(user_id))
    query = {"client_id": settings.github_app_client_id, "redirect_uri": mail.public_link(CALLBACK_PATH), "state": state}
    return f"{_AUTHORIZE_URL}?{urlencode(query)}"


def _check_state(user_id: str, state: str) -> None:
    try:
        payload = json.loads(secrets_box.decrypt(state, context=_state_context(user_id)))
    except Exception as exc:
        raise ConnectionFailedError("That GitHub link isn't valid for your account: connect again") from exc
    if payload.get("expires_at", 0) < time.time():
        raise ConnectionFailedError("That GitHub link expired: connect again")


@dataclass(frozen=True)
class _Tokens:
    access_token: str
    expires_at: float | None
    refresh_token: str | None
    refresh_expires_at: float | None

    @classmethod
    def from_response(cls, data: dict[str, Any], now: float) -> _Tokens:
        if "access_token" not in data:
            raise ConnectionFailedError(f"GitHub refused the connection: {data.get('error_description') or data.get('error') or 'no token'}")

        def at(key: str) -> float | None:
            return now + float(data[key]) if data.get(key) else None

        return cls(data["access_token"], at("expires_in"), data.get("refresh_token"), at("refresh_token_expires_in"))


def _token_context(user_id: str) -> str:
    return f"repo-connection:{GITHUB}:{user_id}"


def _save(user_id: str, account_name: str, tokens: _Tokens) -> None:
    encrypted = secrets_box.encrypt(json.dumps(tokens.__dict__), context=_token_context(user_id))
    db.set_repo_connection(user_id=user_id, provider=GITHUB, account_name=account_name, encrypted_token=encrypted, now=time.time())


def _exchange(fields: dict[str, str]) -> dict[str, Any]:
    settings = get_settings()
    with _http() as client:
        response = client.post(
            _TOKEN_URL,
            data={"client_id": settings.github_app_client_id, "client_secret": settings.github_app_client_secret, **fields},
            headers={"Accept": "application/json"},
        )
    if response.status_code >= 500:
        raise ConnectionFailedError("GitHub didn't answer: try again in a moment")
    return response.json()


def complete(user: dict[str, Any], *, code: str, state: str) -> dict[str, Any]:
    """Redeem GitHub's callback for this user: check the state is theirs, get their tokens, and
    keep them encrypted, with their GitHub login."""
    _check_state(user["id"], state)
    tokens = _Tokens.from_response(_exchange({"code": code, "redirect_uri": mail.public_link(CALLBACK_PATH)}), time.time())
    with _http() as client:
        response = client.get(f"{_API}/user", headers=_api_headers(tokens.access_token))
    if response.status_code != 200:
        raise ConnectionFailedError("GitHub didn't say who you are: connect again")
    login = str(response.json().get("login") or "")
    _save(user["id"], login, tokens)
    auth.audit(user, "connection.connected", user, f"GitHub @{login}")
    return status(user["id"])[0]


def disconnect(user: dict[str, Any]) -> bool:
    """Delete the user's GitHub tokens, and revoke them at GitHub when it answers."""
    connection = db.get_repo_connection(user["id"], GITHUB)
    if connection is None:
        return False
    tokens = _tokens(user["id"], connection)
    db.delete_repo_connection(user["id"], GITHUB)
    if tokens is not None:
        settings = get_settings()
        try:
            with _http() as client:
                client.request(
                    "DELETE",
                    f"{_API}/applications/{settings.github_app_client_id}/grant",
                    auth=(settings.github_app_client_id or "", settings.github_app_client_secret or ""),
                    json={"access_token": tokens.access_token},
                    headers={"Accept": "application/vnd.github+json"},
                )
        except httpx.HTTPError:
            pass  # Deleted here either way; GitHub lets the token lapse.
    auth.audit(user, "connection.disconnected", user, f"GitHub @{connection['account_name']}")
    return True


def status(user_id: str) -> list[dict[str, Any]]:
    """The user's connections as they see them: never a token."""
    return [
        {"provider": row["provider"], "account_name": row["account_name"], "connected_at": row["created_at"]}
        for row in db.list_repo_connections(user_id)
    ]


# Tokens for scans.


class NoAccessError(Exception):
    """The owner's connection can't read the repository, or there's no connection any more."""


def _tokens(user_id: str, connection: dict[str, Any]) -> _Tokens | None:
    try:
        return _Tokens(**json.loads(secrets_box.decrypt(connection["encrypted_token"], context=_token_context(user_id))))
    except Exception:  # noqa: BLE001 - a key that changed, or a garbled row: as if not connected
        return None


def token_for(user_id: str | None) -> str | None:
    """The user's GitHub access token, refreshed first when it's about to expire; None without a
    working connection (one GitHub won't refresh any more is deleted)."""
    if not user_id or not secrets_box.is_configured():
        return None
    connection = db.get_repo_connection(user_id, GITHUB)
    tokens = _tokens(user_id, connection) if connection else None
    if tokens is None:
        return None
    now = time.time()
    if tokens.expires_at is not None and tokens.expires_at - _REFRESH_MARGIN_SECONDS <= now:
        if not tokens.refresh_token or (tokens.refresh_expires_at is not None and tokens.refresh_expires_at <= now):
            db.delete_repo_connection(user_id, GITHUB)
            return None
        try:
            tokens = _Tokens.from_response(_exchange({"grant_type": "refresh_token", "refresh_token": tokens.refresh_token}), now)
        except ConnectionFailedError:
            db.delete_repo_connection(user_id, GITHUB)
            return None
        _save(user_id, connection["account_name"], tokens)
    return tokens.access_token


def _api_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


def github_repository(target: str) -> tuple[str, str] | None:
    """(owner, repository) of a GitHub repository or raw file link; None for anything else."""
    parts = urlsplit(target)
    segments = [unquote(segment) for segment in parts.path.split("/") if segment]
    if parts.scheme != "https" or len(segments) < 2:
        return None
    if parts.hostname in ("github.com", "raw.githubusercontent.com"):
        return segments[0], segments[1].removesuffix(".git")
    return None


def private_for(user_id: str | None, target: str) -> bool:
    """Whether the target is a private GitHub repository its owner's connection reads: the scan
    then uses their token. False for anything public, not on GitHub, or without a connection;
    NoAccessError when they're connected and GitHub won't show them the repository."""
    repository = github_repository(target)
    token = token_for(user_id) if repository and available() else None
    if repository is None or token is None:
        return False
    owner, name = repository
    with _http() as client:
        response = client.get(f"{_API}/repos/{owner}/{name}", headers=_api_headers(token))
    if response.status_code == 200:
        return bool(response.json().get("private"))
    if response.status_code in (403, 404):
        where = f" ({manage_url()})" if manage_url() else ""
        raise NoAccessError(f"Your GitHub connection can't read {owner}/{name}: give the app access to it on GitHub{where}, or check the link")
    raise NoAccessError("GitHub didn't answer about this repository: try again in a moment")


# Picking a repository to scan.

_PAGE_SIZE = 100
# Listing stops here, so a user in large organizations still gets an answer quickly; they can still
# paste any other link.
MAX_LISTED_REPOSITORIES = 1000


def _get(client: httpx.Client, path: str, token: str, page: int) -> dict[str, Any]:
    response = client.get(f"{_API}{path}", params={"per_page": _PAGE_SIZE, "page": page}, headers=_api_headers(token))
    if response.status_code == 401:
        raise NoAccessError("GitHub refused your connection: connect GitHub again on your account page")
    if response.status_code != 200:
        raise NoAccessError("GitHub didn't answer: try again in a moment")
    return response.json()


def repositories(user_id: str) -> tuple[list[dict[str, Any]], bool]:
    """The repositories the user's connection reads, most recently pushed first: those of every
    installation of the app they can see, which GitHub limits to what both they and it can read.
    With whether the list stopped at MAX_LISTED_REPOSITORIES."""
    token = token_for(user_id)
    if token is None:
        raise NoAccessError("Connect GitHub on your account page to pick one of your repositories")
    found: dict[str, dict[str, Any]] = {}
    with _http() as client:
        installations = _get(client, "/user/installations", token, 1).get("installations", [])
        for installation in installations:
            page = 1
            # One past the cap tells that there were more.
            while len(found) <= MAX_LISTED_REPOSITORIES:
                listed = _get(client, f"/user/installations/{installation['id']}/repositories", token, page)
                for repo in listed.get("repositories", []):
                    found.setdefault(repo["full_name"], repo)
                if page * _PAGE_SIZE >= listed.get("total_count", 0):
                    break
                page += 1
    ordered = sorted(found.values(), key=lambda repo: repo.get("pushed_at") or "", reverse=True)
    return [
        {"full_name": repo["full_name"], "url": repo["html_url"], "private": bool(repo.get("private")), "description": repo.get("description")}
        for repo in ordered[:MAX_LISTED_REPOSITORIES]
    ], len(found) > MAX_LISTED_REPOSITORIES


def require_token(user_id: str | None) -> str:
    """The token a private-source scan runs with: its owner's, now."""
    token = token_for(user_id)
    if token is None:
        raise NoAccessError("This inspection reads a private GitHub repository: connect GitHub on your account page, then inspect again")
    return token


def auth_headers(token: str) -> dict[str, dict[str, str]]:
    """The Authorization header for each GitHub host a scan of a private repository reaches: Git over
    HTTPS takes the token as a password, raw files as a token."""
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return {"github.com": {"Authorization": f"Basic {basic}"}, "raw.githubusercontent.com": {"Authorization": f"token {token}"}}


def _git_env(token: str) -> dict[str, str]:
    """The clone's own environment: the header as Git config from variables, so it's neither in
    the command line nor written to the clone; and never a prompt."""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": tempfile.gettempdir(),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraHeader",
        "GIT_CONFIG_VALUE_0": f"Authorization: {auth_headers(token)['github.com']['Authorization']}",
    }


def _git(args: list[str], token: str, *, cwd: str | None = None) -> str:
    try:
        done = subprocess.run(
            ["git", *args], env=_git_env(token), cwd=cwd, capture_output=True, text=True, timeout=_CLONE_TIMEOUT_SECONDS, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Cloning the private repository took too long") from exc
    if done.returncode != 0:
        detail = done.stderr.strip().splitlines()[-1] if done.stderr.strip() else "git failed"
        if any(sign in detail for sign in ("could not read Username", "Authentication failed", "not found", "403")):
            where = f" ({manage_url()})" if manage_url() else ""
            raise RuntimeError(f"Your GitHub connection can't read this repository any more: check the app's access to it on GitHub{where}")
        # Git's own message otherwise, which never holds the header.
        raise RuntimeError(f"Couldn't clone the private repository: {detail}")
    return done.stdout


def _tree_parts(target: str) -> tuple[str, list[str]] | None:
    """(owner/repo, the segments after /tree/) of a GitHub folder link; None for a repository link."""
    segments = [unquote(segment) for segment in urlsplit(target).path.split("/") if segment]
    if len(segments) >= 4 and segments[2] == "tree":
        rest = segments[3:]
        if any(part in {"", ".", ".."} or "\\" in part for part in rest):
            raise ValueError("The link's folder must stay within the repository")
        return f"{segments[0]}/{segments[1].removesuffix('.git')}", rest
    return None


def _size(path: Path) -> int:
    return sum(entry.stat().st_size for entry in path.rglob("*") if entry.is_file() and not entry.is_symlink())


def _clone(target: str, token: str, into: Path) -> Path:
    owner, name = github_repository(target) or ("", "")
    repository_url = f"https://github.com/{owner}/{name}.git"
    tree = _tree_parts(target)
    branch, folder = None, PurePosixPath()
    if tree is not None:
        # As skillspector does: the longest branch or tag naming the start of the path.
        refs = {
            line.split("\t", 1)[1].removeprefix("refs/heads/").removeprefix("refs/tags/").removesuffix("^{}")
            for line in _git(["ls-remote", "--heads", "--tags", repository_url], token).splitlines()
            if "\t" in line
        }
        _, segments = tree
        for end in range(len(segments), 0, -1):
            if "/".join(segments[:end]) in refs:
                branch, folder = "/".join(segments[:end]), PurePosixPath(*segments[end:])
                break
        else:
            raise ValueError(f"The link doesn't name a branch or tag of {owner}/{name}")
    clone_dir = into / "repo"
    args = ["-c", "core.symlinks=false", "clone", "--depth", "1", f"--filter=blob:limit={MAX_COPY_BYTES}"]
    _git([*args, *(["--branch", branch] if branch else []), repository_url, str(clone_dir)], token)
    if _size(clone_dir) > MAX_COPY_BYTES:
        raise RuntimeError(f"The repository is larger than {MAX_COPY_BYTES // (1024 * 1024)} MB")
    selected = (clone_dir / folder).resolve()
    if not selected.is_relative_to(clone_dir.resolve()) or not selected.is_dir():
        raise ValueError("The link's folder doesn't exist in the repository")
    return selected


def _download(target: str, token: str, into: Path) -> Path:
    name = PurePosixPath(urlsplit(target).path).name or "SKILL.md"
    path = into / name
    with _http() as client, client.stream("GET", target, headers={"Authorization": f"token {token}"}) as response:
        if response.status_code != 200:
            raise RuntimeError(f"Couldn't fetch the private file ({response.status_code})")
        written = 0
        with path.open("wb") as file:
            for chunk in response.iter_bytes():
                written += len(chunk)
                if written > MAX_COPY_BYTES:
                    raise RuntimeError("The file is too large to inspect")
                file.write(chunk)
    return path


@asynccontextmanager
async def local_copy(target: str, token: str) -> AsyncIterator[str]:
    """A copy of a private GitHub repository, folder or file, fetched with the token, for the time
    of a scan; deleted afterwards."""
    into = Path(tempfile.mkdtemp(prefix="inskect-private-"))
    try:
        fetch = _download if urlsplit(target).hostname == "raw.githubusercontent.com" else _clone
        yield str(await asyncio.to_thread(fetch, target, token, into))
    finally:
        shutil.rmtree(into, ignore_errors=True)
