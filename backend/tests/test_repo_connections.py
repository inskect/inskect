from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import anyio
import httpx
import pytest
from fastapi.testclient import TestClient

from app import db, repo_connections, scanner, secrets_box
from app.auth import passwords
from app.core.config import get_settings
from app.main import app

PASSWORD = "correct horse battery"
PRIVATE = "https://github.com/acme/secret-skills"
PUBLIC = "https://github.com/acme/open-skills"
TOKEN = "ghu_alicesusertoken0123456789"


@pytest.fixture(autouse=True)
def _fast_hashing(monkeypatch):
    monkeypatch.setattr(passwords, "_N", 2**10)
    passwords.dummy_hash.cache_clear()
    yield
    passwords.dummy_hash.cache_clear()


class FakeGitHub:
    """GitHub's OAuth and REST endpoints, as the app calls them: who may read which repository."""

    def __init__(self) -> None:
        self.users = {"code-alice": ("alice-gh", TOKEN), "code-bob": ("bob-gh", "ghu_bobstoken")}
        self.readable = {TOKEN: {"acme/secret-skills", "acme/open-skills"}, "ghu_bobstoken": {"acme/open-skills"}}
        self.private = {"acme/secret-skills"}
        self.pushed_at = {"acme/secret-skills": "2026-09-30T10:00:00Z", "acme/open-skills": "2026-06-01T10:00:00Z"}
        self.expires_in = 28800
        self.refresh_ok = True
        self.revoked: list[str] = []
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/login/oauth/access_token":
            form = parse_qs(request.content.decode())
            if form.get("grant_type") == ["refresh_token"]:
                if not self.refresh_ok:
                    return httpx.Response(200, json={"error": "bad_refresh_token"})
                return httpx.Response(200, json={"access_token": TOKEN, "expires_in": self.expires_in, "refresh_token": "ghr_new", "refresh_token_expires_in": 15897600})
            account = self.users.get(form["code"][0])
            if account is None:
                return httpx.Response(200, json={"error": "bad_verification_code", "error_description": "The code passed is incorrect or expired."})
            return httpx.Response(200, json={"access_token": account[1], "expires_in": self.expires_in, "refresh_token": "ghr_1", "refresh_token_expires_in": 15897600})
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if path == "/user":
            login = next(login for login, value in self.users.values() if value == token)
            return httpx.Response(200, json={"login": login})
        if path.startswith("/repos/"):
            repository = path.removeprefix("/repos/")
            if repository not in self.readable.get(token, set()):
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json={"full_name": repository, "private": repository in self.private})
        if path == "/user/installations":
            return httpx.Response(200, json={"total_count": 1, "installations": [{"id": 7}]} if self.readable.get(token) else {"total_count": 0, "installations": []})
        if path == "/user/installations/7/repositories":
            page, per_page = int(request.url.params["page"]), int(request.url.params["per_page"])
            readable = sorted(self.readable.get(token, set()))
            repositories = [
                {"full_name": name, "html_url": f"https://github.com/{name}", "private": name in self.private, "description": None, "pushed_at": self.pushed_at.get(name)}
                for name in readable[(page - 1) * per_page : page * per_page]
            ]
            return httpx.Response(200, json={"total_count": len(readable), "repositories": repositories})
        if path.endswith("/grant") and request.method == "DELETE":
            self.revoked.append(json.loads(request.content)["access_token"])
            return httpx.Response(204)
        return httpx.Response(404)


@pytest.fixture
def github(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(repo_connections, "_http", lambda: httpx.Client(transport=httpx.MockTransport(fake.handle)))
    return fake


@pytest.fixture
def client(temp_db, fake_runner, github, monkeypatch):
    settings = get_settings()
    for name, value in {
        "auth": "accounts",
        "allow_signup": None,
        "secret_key": secrets_box.generate_key(),
        "public_url": "https://inskect.example.com",
        "github_app_client_id": "Iv1.client",
        "github_app_client_secret": "app-secret",
        "github_app_slug": "inskect-test",
        "daily_scan_quota": None,
        "concurrent_scan_quota": None,
    }.items():
        monkeypatch.setattr(settings, name, value)
    client = TestClient(app)
    client.runner = fake_runner
    return client


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _accounts(client) -> tuple[str, str, str]:
    """The admin, alice and bob, signed in."""
    admin = client.post("/auth/setup", json={"email": "admin@example.com", "password": PASSWORD}).json()["token"]
    sessions = []
    for email in ("alice@example.com", "bob@example.com"):
        client.post("/admin/users", json={"email": email, "password": PASSWORD}, headers=_bearer(admin))
        sessions.append(client.post("/auth/login", json={"email": email, "password": PASSWORD}).json()["token"])
    return admin, sessions[0], sessions[1]


def _user_id(client, session: str) -> str:
    return client.get("/auth/session", headers=_bearer(session)).json()["user"]["id"]


def _connect(client, session: str, code: str = "code-alice"):
    start = client.get("/account/connections/github/start", headers=_bearer(session)).json()["url"]
    state = parse_qs(urlsplit(start).query)["state"][0]
    return client.post("/account/connections/github/callback", json={"code": code, "state": state}, headers=_bearer(session))


# Connecting


def test_connecting_keeps_the_tokens_encrypted_and_shows_only_the_account(client, github):
    _, alice, _ = _accounts(client)

    start = client.get("/account/connections/github/start", headers=_bearer(alice)).json()["url"]
    query = parse_qs(urlsplit(start).query)
    assert start.startswith("https://github.com/login/oauth/authorize?")
    assert query["redirect_uri"] == ["https://inskect.example.com/api/account/connections/github/callback"]
    connected = client.post("/account/connections/github/callback", json={"code": "code-alice", "state": query["state"][0]}, headers=_bearer(alice))

    assert connected.status_code == 200 and connected.json()["account_name"] == "alice-gh"
    listed = client.get("/account/connections", headers=_bearer(alice)).json()
    assert listed["github"]["connection"]["account_name"] == "alice-gh"
    assert listed["github"]["manage_url"] == "https://github.com/apps/inskect-test/installations/new"
    stored = db.get_repo_connection(_user_id(client, alice), "github")
    assert TOKEN not in stored["encrypted_token"] and TOKEN not in json.dumps(listed)
    entries, _ = db.list_audit(10, 0)
    assert any(entry["action"] == "connection.connected" and entry["detail"] == "GitHub @alice-gh" for entry in entries)


def test_a_state_only_works_for_the_user_it_was_made_for(client):
    _, alice, bob = _accounts(client)
    start = client.get("/account/connections/github/start", headers=_bearer(alice)).json()["url"]
    state = parse_qs(urlsplit(start).query)["state"][0]

    refused = client.post("/account/connections/github/callback", json={"code": "code-alice", "state": state}, headers=_bearer(bob))

    assert refused.status_code == 400 and "isn't valid for your account" in refused.json()["detail"]
    assert client.get("/account/connections", headers=_bearer(bob)).json()["github"]["connection"] is None


def test_an_expired_state_or_a_bad_code_is_refused(client):
    _, alice, _ = _accounts(client)
    assert _connect(client, alice, code="code-nobody").json()["detail"].startswith("GitHub refused the connection")

    # A state as start_url makes them, ten minutes old.
    payload = json.dumps({"nonce": "n", "expires_at": time.time() - 1})
    state = secrets_box.encrypt(payload, context=repo_connections._state_context(_user_id(client, alice)))
    assert "expired" in client.post("/account/connections/github/callback", json={"code": "code-alice", "state": state}, headers=_bearer(alice)).json()["detail"]


def test_connecting_needs_the_app_set_up(client, monkeypatch):
    _, alice, _ = _accounts(client)
    monkeypatch.setattr(get_settings(), "github_app_client_secret", None)

    assert client.get("/account/connections", headers=_bearer(alice)).json()["github"]["available"] is False
    assert client.get("/account/connections/github/start", headers=_bearer(alice)).status_code == 404


def test_an_expired_token_is_refreshed_and_a_dead_one_disconnects(client, github, monkeypatch):
    _, alice, _ = _accounts(client)
    github.expires_in = 60  # Inside the refresh margin.
    _connect(client, alice)
    alice_id = _user_id(client, alice)

    assert repo_connections.token_for(alice_id) == TOKEN
    assert any(parse_qs(request.content.decode()).get("grant_type") == ["refresh_token"] for request in github.requests)

    github.refresh_ok = False
    assert repo_connections.token_for(alice_id) is None
    assert db.get_repo_connection(alice_id, "github") is None


def test_disconnecting_deletes_and_revokes_the_token(client, github):
    _, alice, _ = _accounts(client)
    _connect(client, alice)

    assert client.delete("/account/connections/github", headers=_bearer(alice)).status_code == 204

    assert db.get_repo_connection(_user_id(client, alice), "github") is None
    assert github.revoked == [TOKEN]


def test_deleting_the_account_deletes_and_revokes_its_connection(client, github):
    admin, alice, _ = _accounts(client)
    _connect(client, alice)
    alice_id = _user_id(client, alice)

    client.delete(f"/admin/users/{alice_id}", headers=_bearer(admin))

    assert db.get_repo_connection(alice_id, "github") is None
    assert github.revoked == [TOKEN]


def test_an_api_token_cant_manage_connections(client):
    _, alice, _ = _accounts(client)
    token = client.post("/account/tokens", json={"name": "CI", "password": PASSWORD}, headers=_bearer(alice)).json()["token"]

    assert client.get("/account/connections/github/start", headers=_bearer(token)).status_code == 403


# Picking a repository


def test_the_picker_lists_what_the_connection_reads_most_recent_first(client, github):
    _, alice, bob = _accounts(client)
    _connect(client, alice)
    _connect(client, bob, "code-bob")

    listed = client.get("/account/connections/github/repositories", headers=_bearer(alice)).json()

    assert listed == {
        "repositories": [
            {"full_name": "acme/secret-skills", "url": PRIVATE, "private": True, "description": None},
            {"full_name": "acme/open-skills", "url": PUBLIC, "private": False, "description": None},
        ],
        "truncated": False,
    }
    bobs = client.get("/account/connections/github/repositories", headers=_bearer(bob)).json()["repositories"]
    assert [repo["full_name"] for repo in bobs] == ["acme/open-skills"]


def test_the_picker_pages_through_and_stops_at_the_cap(client, github, monkeypatch):
    _, alice, _ = _accounts(client)
    _connect(client, alice)
    github.readable[TOKEN] = {f"acme/skill-{n:03}" for n in range(250)}
    monkeypatch.setattr(repo_connections, "MAX_LISTED_REPOSITORIES", 150)

    listed = client.get("/account/connections/github/repositories", headers=_bearer(alice)).json()

    assert len(listed["repositories"]) == 150 and listed["truncated"] is True
    pages = [request.url.params["page"] for request in github.requests if request.url.path == "/user/installations/7/repositories"]
    assert pages == ["1", "2"]

    monkeypatch.setattr(repo_connections, "MAX_LISTED_REPOSITORIES", 250)
    listed = client.get("/account/connections/github/repositories", headers=_bearer(alice)).json()
    assert len(listed["repositories"]) == 250 and listed["truncated"] is False


def test_the_picker_needs_a_connection(client):
    _, alice, _ = _accounts(client)
    token = client.post("/account/tokens", json={"name": "CI", "password": PASSWORD}, headers=_bearer(alice)).json()["token"]

    response = client.get("/account/connections/github/repositories", headers=_bearer(alice))

    assert response.status_code == 409 and "Connect GitHub" in response.json()["detail"]
    assert client.get("/account/connections/github/repositories", headers=_bearer(token)).status_code == 403


# Scanning


def test_a_private_repository_is_scanned_with_its_owners_connection_only(client, github):
    _, alice, bob = _accounts(client)
    _connect(client, alice)

    queued = client.post("/scan", json={"target": PRIVATE}, headers=_bearer(alice))
    assert queued.status_code == 200
    job = client.runner.submitted[-1]
    assert (job.private_source, job.owner_id) == (True, _user_id(client, alice))
    assert db.get_scan(job.id)["private_source"]

    # Bob, not connected: the link is scanned as a public one, without anyone's token.
    client.post("/scan", json={"target": PRIVATE}, headers=_bearer(bob))
    assert client.runner.submitted[-1].private_source is False
    # Bob, connected, but GitHub doesn't show him the repository: refused, saying why.
    _connect(client, bob, code="code-bob")
    refused = client.post("/scan", json={"target": PRIVATE}, headers=_bearer(bob))
    assert refused.status_code == 422 and "can't read acme/secret-skills" in refused.json()["detail"]


def test_a_public_repository_is_scanned_without_the_token(client):
    _, alice, _ = _accounts(client)
    _connect(client, alice)

    client.post("/scan", json={"target": PUBLIC + "/tree/main/pdf"}, headers=_bearer(alice))

    assert client.runner.submitted[-1].private_source is False


def test_a_scan_after_disconnecting_fails_saying_to_connect_again(client, monkeypatch):
    _, alice, _ = _accounts(client)
    _connect(client, alice)
    client.post("/scan", json={"target": PRIVATE}, headers=_bearer(alice))
    job = client.runner.submitted[-1]
    client.delete("/account/connections/github", headers=_bearer(alice))
    monkeypatch.setattr(scanner, "_invoke_graph", lambda *args, **kwargs: pytest.fail("scanned without a token"))

    anyio.run(scanner.run_job, job)

    scan = db.get_scan(job.id)
    assert scan["status"] == "error" and "connect GitHub on your account page" in scan["error"]


@pytest.fixture
def fake_git(tmp_path, monkeypatch) -> Path:
    """A `git` on the PATH that records each call's arguments and environment, and clones a skill."""
    calls = tmp_path / "git-calls.jsonl"
    script = tmp_path / "bin" / "git"
    script.parent.mkdir()
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys, pathlib\n"
        f"open({str(calls)!r}, 'a').write(json.dumps({{'args': sys.argv[1:], 'env': dict(os.environ)}}) + '\\n')\n"
        "if 'ls-remote' in sys.argv:\n"
        "    print('abc\\trefs/heads/main'); print('def\\trefs/heads/feature/x')\n"
        "else:\n"
        "    root = pathlib.Path(sys.argv[-1]); (root / 'pdf').mkdir(parents=True)\n"
        "    (root / 'pdf' / 'SKILL.md').write_text('# PDF')\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{script.parent}{os.pathsep}{os.environ['PATH']}")
    return calls


def test_a_private_repository_is_cloned_with_the_token_in_the_clones_environment_only(fake_git):
    async def copy():
        async with repo_connections.local_copy(PRIVATE + "/tree/feature/x/pdf", TOKEN) as path:
            return Path(path).name, (Path(path) / "SKILL.md").read_text()

    assert anyio.run(copy) == ("pdf", "# PDF")
    calls = [json.loads(line) for line in fake_git.read_text().splitlines()]
    clone = calls[-1]
    assert "--branch" in clone["args"] and clone["args"][clone["args"].index("--branch") + 1] == "feature/x"
    # Never on the command line, nor in this process's environment.
    assert all(TOKEN not in " ".join(call["args"]) for call in calls)
    assert TOKEN not in json.dumps(dict(os.environ))
    header = clone["env"]["GIT_CONFIG_VALUE_0"]
    assert clone["env"]["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraHeader" and header.startswith("Authorization: Basic ")
    assert clone["env"]["GIT_TERMINAL_PROMPT"] == "0"



# Privacy of the result


def _finished_private_scan(client, alice: str) -> str:
    _connect(client, alice)
    scan_id = client.post("/scan", json={"target": PRIVATE}, headers=_bearer(alice)).json()["id"]
    db.update_scan(id=scan_id, status="done", finished_at=time.time(), result={"risk_assessment": {"score": 2, "recommendation": "SAFE"}, "issues": []}, error=None)
    return scan_id


def test_a_private_scan_is_shared_or_badged_only_once_confirmed(client):
    _, alice, _ = _accounts(client)
    scan_id = _finished_private_scan(client, alice)

    refused = client.post(f"/scan/{scan_id}/share", headers=_bearer(alice))
    assert refused.status_code == 409 and "private repository" in refused.json()["detail"]
    shared = client.post(f"/scan/{scan_id}/share", json={"confirm_private": True}, headers=_bearer(alice))
    assert shared.status_code == 200

    assert client.post(f"/scan/{scan_id}/badge", headers=_bearer(alice)).status_code == 409
    assert client.post(f"/scan/{scan_id}/badge", json={"confirm_private": True}, headers=_bearer(alice)).status_code == 204


def test_only_its_owner_opens_a_private_scan_even_an_admin(client):
    admin, alice, _ = _accounts(client)
    scan_id = _finished_private_scan(client, alice)

    assert client.get(f"/scan/{scan_id}", headers=_bearer(alice)).json()["private_source"] is True
    for path in (f"/scan/{scan_id}", f"/scan/{scan_id}/export", f"/scan/{scan_id}/logs"):
        assert client.get(path, headers=_bearer(admin)).status_code == 403
    assert client.post(f"/scan/{scan_id}/rescan", headers=_bearer(admin)).status_code == 403
    # The admin sees that it exists, and may delete it.
    assert scan_id in [item["id"] for item in client.get("/scan", headers=_bearer(admin)).json()["items"]]
    assert client.delete(f"/scan/{scan_id}", headers=_bearer(admin)).status_code == 204
