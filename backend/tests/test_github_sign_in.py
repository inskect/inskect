from __future__ import annotations

import hashlib
import json
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from app import db, repo_connections, secrets_box
from app.auth import github_sign_in, passwords
from app.core.config import get_settings
from app.main import app

PASSWORD = "correct horse battery"
NONCE = "a-nonce-from-the-web-apps-cookie"


@pytest.fixture(autouse=True)
def _fast_hashing(monkeypatch):
    monkeypatch.setattr(passwords, "_N", 2**10)
    passwords.dummy_hash.cache_clear()
    yield
    passwords.dummy_hash.cache_clear()


class FakeGitHub:
    """GitHub's OAuth and the API calls sign-in makes: who the user is, and their emails."""

    def __init__(self) -> None:
        # code: (numeric id, login, emails)
        self.accounts = {
            "code-octo": [101, "octo", [{"email": "Octo@Example.com", "primary": True, "verified": True}]],
            "code-alice": [202, "alice-gh", [{"email": "alice@example.com", "primary": True, "verified": True}]],
            "code-unverified": [303, "nomail", [{"email": "nomail@example.com", "primary": True, "verified": False}]],
        }
        self.revoked: list[str] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/login/oauth/access_token":
            code = parse_qs(request.content.decode())["code"][0]
            if code not in self.accounts:
                return httpx.Response(200, json={"error": "bad_verification_code"})
            return httpx.Response(200, json={"access_token": f"ghu_{code}"})
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        account = self.accounts.get(token.removeprefix("ghu_"))
        if path == "/user" and account:
            return httpx.Response(200, json={"id": account[0], "login": account[1]})
        if path == "/user/emails" and account:
            return httpx.Response(200, json=account[2])
        if path.endswith("/token") and request.method == "DELETE":
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
        "login_rate_limit": 1000,
    }.items():
        monkeypatch.setattr(settings, name, value)
    client = TestClient(app)
    client.post("/auth/setup", json={"email": "admin@example.com", "password": PASSWORD})
    client.admin = client.post("/auth/login", json={"email": "admin@example.com", "password": PASSWORD}).json()["token"]
    return client


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _state(client, *, link_as: str | None = None, nonce: str = NONCE) -> str:
    body = {"nonce_hash": hashlib.sha256(nonce.encode()).hexdigest()}
    if link_as:
        response = client.post("/account/sign-in-methods/github/start", json=body, headers=_bearer(link_as))
    else:
        response = client.post("/auth/github/start", json=body)
    assert response.status_code == 200, response.text
    url = urlsplit(response.json()["url"])
    query = parse_qs(url.query)
    assert url.netloc == "github.com" and query["redirect_uri"] == ["https://inskect.example.com/api/auth/github/callback"]
    return query["state"][0]


def _github(client, code: str, *, link_as: str | None = None, nonce: str = NONCE, state: str | None = None):
    state = state or _state(client, link_as=link_as)
    headers = _bearer(link_as) if link_as else {}
    return client.post("/auth/github/callback", json={"code": code, "state": state, "nonce": nonce}, headers=headers)


def _methods(client, session: str) -> dict:
    return client.get("/account/sign-in-methods", headers=_bearer(session)).json()


def test_signing_up_with_github_makes_an_account_without_a_password(client, github):
    response = _github(client, "code-octo")

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "signed_up" and body["user"]["email"] == "octo@example.com"
    assert client.get("/auth/session", headers=_bearer(body["token"])).json()["user"]["email"] == "octo@example.com"
    assert _methods(client, body["token"]) == {"password": False, "github": {"login": "octo", "linked_at": pytest.approx(time.time(), abs=60)}, "github_available": True}
    # Its token served only to read who signed in: revoked straight away, never kept.
    assert github.revoked == ["ghu_code-octo"]
    assert db.list_repo_connections(body["user"]["id"]) == []
    activity = client.get("/admin/activity", headers=_bearer(client.admin)).json()["items"]
    assert ("account.created", "signed up with GitHub") in [(e["action"], e["detail"]) for e in activity]


def test_signing_in_again_finds_the_account_by_its_github_id_after_a_rename(client, github):
    first = _github(client, "code-octo").json()
    github.accounts["code-octo"][1] = "octo-renamed"
    github.accounts["code-octo"][2] = [{"email": "new@example.com", "primary": True, "verified": True}]

    again = _github(client, "code-octo").json()

    assert again["outcome"] == "signed_in"
    assert again["user"]["id"] == first["user"]["id"] and again["token"] != first["token"]
    assert _methods(client, again["token"])["github"]["login"] == "octo-renamed"


def test_a_matching_email_never_links_github_to_an_existing_account(client):
    client.post("/admin/users", json={"email": "alice@example.com", "password": PASSWORD}, headers=_bearer(client.admin))

    response = _github(client, "code-alice")

    assert response.status_code == 409
    assert "sign in with its password, then link GitHub" in response.json()["detail"]
    assert db.get_identity_user("github", "202") is None


def test_a_suspended_account_cant_sign_in_with_github(client):
    user_id = _github(client, "code-octo").json()["user"]["id"]
    client.patch(f"/admin/users/{user_id}", json={"status": "suspended"}, headers=_bearer(client.admin))

    response = _github(client, "code-octo")

    assert (response.status_code, response.json()["detail"]) == (403, github_sign_in.SUSPENDED)


def test_closed_sign_up_refuses_a_new_github_account(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "allow_signup", False)

    response = _github(client, "code-octo")

    assert (response.status_code, response.json()["detail"]) == (403, "Ask an admin of this server for an account")


def test_an_account_needs_a_verified_email(client):
    response = _github(client, "code-unverified")

    assert response.status_code == 400 and "verified primary email" in response.json()["detail"]


@pytest.mark.parametrize("tamper", ["garbage state", "another browser", "replayed", "expired"])
def test_a_bad_or_replayed_state_is_refused(client, monkeypatch, tamper):
    state = _state(client)
    if tamper == "garbage state":
        state = "v1:not:encrypted"
    if tamper == "replayed":
        assert _github(client, "code-octo", state=state).status_code == 200
    if tamper == "expired":
        real_time = time.time
        monkeypatch.setattr(github_sign_in.time, "time", lambda: real_time() + github_sign_in.STATE_SECONDS + 1)

    response = _github(client, "code-octo", state=state, nonce="someone-elses-nonce" if tamper == "another browser" else NONCE)

    assert response.status_code == 400


def test_linking_and_unlinking_github_from_the_account_page(client):
    client.post("/admin/users", json={"email": "alice@example.com", "password": PASSWORD}, headers=_bearer(client.admin))
    alice = client.post("/auth/login", json={"email": "alice@example.com", "password": PASSWORD}).json()["token"]

    linked = _github(client, "code-alice", link_as=alice)

    assert linked.json() == {"outcome": "linked", "token": None, "expires_at": None, "user": None}
    assert _methods(client, alice)["github"]["login"] == "alice-gh"
    assert _github(client, "code-alice").json()["user"]["email"] == "alice@example.com"
    # Another account can't take the same GitHub account.
    other = _github(client, "code-octo").json()["token"]
    assert _github(client, "code-alice", link_as=other).status_code == 409

    assert client.delete("/account/sign-in-methods/github", headers=_bearer(alice)).status_code == 204
    assert _methods(client, alice)["github"] is None
    activity = [e["action"] for e in client.get("/admin/activity", headers=_bearer(client.admin)).json()["items"]]
    assert "auth.github_linked" in activity and "auth.github_unlinked" in activity


def test_the_last_way_to_sign_in_cant_be_removed(client):
    session = _github(client, "code-octo").json()["token"]

    response = client.delete("/account/sign-in-methods/github", headers=_bearer(session))

    assert response.status_code == 409 and "set a password first" in response.json()["detail"]


def test_linking_is_for_the_account_that_started_it(client):
    octo = _github(client, "code-octo").json()["token"]
    state = _state(client, link_as=octo)
    client.post("/admin/users", json={"email": "alice@example.com", "password": PASSWORD}, headers=_bearer(client.admin))
    alice = client.post("/auth/login", json={"email": "alice@example.com", "password": PASSWORD}).json()["token"]

    response = client.post("/auth/github/callback", json={"code": "code-alice", "state": state, "nonce": NONCE}, headers=_bearer(alice))

    assert response.status_code == 403


def test_without_a_password_a_recent_sign_in_stands_in_for_it(client, monkeypatch):
    session = _github(client, "code-octo").json()["token"]

    assert client.post("/account/tokens", json={"name": "CI"}, headers=_bearer(session)).status_code == 201

    real_time = time.time
    monkeypatch.setattr(github_sign_in.time, "time", lambda: real_time() + github_sign_in.RECENT_SIGN_IN_SECONDS + 1)
    response = client.post("/account/tokens", json={"name": "CI 2"}, headers=_bearer(session))
    assert (response.status_code, response.json()["detail"]) == (403, "Sign in with GitHub again, then do this within 10 minutes")


def test_a_password_sign_in_never_works_for_an_account_without_one(client):
    _github(client, "code-octo")

    assert client.post("/auth/login", json={"email": "octo@example.com", "password": ""}).status_code in (401, 422)
    assert client.post("/auth/login", json={"email": "octo@example.com", "password": "anything at all"}).status_code == 401


def test_without_the_github_app_nothing_about_github_sign_in_is_offered(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "github_app_client_id", None)

    assert client.post("/auth/github/start", json={"nonce_hash": "0" * 64}).status_code == 404
    assert client.get("/auth/session").json()["features"]["github"] is False
