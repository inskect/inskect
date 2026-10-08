from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import claude_key, db, scanner, secrets_box
from app.auth import passwords
from app.core.config import Settings, get_settings
from app.main import app
from app.scanner import LLMConfig

PASSWORD = "correct horse battery"
KEY = "sk-ant-api03-real-secret-key-abcd1234"


class _Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


@pytest.fixture(autouse=True)
def _fast_hashing(monkeypatch):
    monkeypatch.setattr(passwords, "_N", 2**10)
    passwords.dummy_hash.cache_clear()
    yield
    passwords.dummy_hash.cache_clear()


@pytest.fixture
def anthropic(monkeypatch):
    """Stands in for Anthropic's key check; set .status to what it answers."""
    calls = []

    def get(url, headers, timeout):
        calls.append(headers["x-api-key"])
        return _Response(anthropic.status)

    anthropic.status = 200
    anthropic.calls = calls
    monkeypatch.setattr(claude_key.httpx, "get", get)
    return anthropic


@pytest.fixture
def client(temp_db, fake_runner, anthropic, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "auth", "accounts")
    monkeypatch.setattr(settings, "secret_key", secrets_box.generate_key())
    client = TestClient(app)
    client.submitted = fake_runner.submitted
    return client


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _sign_up(client, email="alice@example.com") -> tuple[str, str]:
    body = client.post("/auth/signup", json={"email": email, "password": PASSWORD}).json()
    return body["user"]["id"], body["token"]


def _connect(client, token, key=KEY):
    return client.put("/account/claude", json={"api_key": key}, headers=_bearer(token))


# Encryption


def test_secrets_round_trip_and_are_bound_to_their_context(monkeypatch):
    settings = Settings(_env_file=None, secret_key=secrets_box.generate_key())

    token = secrets_box.encrypt("hello", context="user:1", settings=settings)

    assert "hello" not in token
    assert secrets_box.decrypt(token, context="user:1", settings=settings) == "hello"
    with pytest.raises(secrets_box.SecretBoxError):
        secrets_box.decrypt(token, context="user:2", settings=settings)
    other = Settings(_env_file=None, secret_key=secrets_box.generate_key())
    with pytest.raises(secrets_box.SecretBoxError):
        secrets_box.decrypt(token, context="user:1", settings=other)


@pytest.mark.parametrize("value", [None, "", "not base64 !!", "c2hvcnQ"])
def test_a_missing_or_malformed_secret_key_is_not_configured(value):
    assert not secrets_box.is_configured(Settings(_env_file=None, secret_key=value))


# Connecting a key


def test_connecting_a_key_checks_it_and_stores_it_encrypted(client, anthropic):
    user_id, token = _sign_up(client)

    response = _connect(client, token)

    assert response.status_code == 200
    assert response.json()["hint"] == "…1234"
    assert KEY not in response.text
    assert anthropic.calls == [KEY]
    stored = db.get_llm_credential(user_id)
    assert KEY not in stored["encrypted_key"]
    assert client.get("/account/claude", headers=_bearer(token)).json()["hint"] == "…1234"
    session = client.get("/auth/session", headers=_bearer(token)).json()
    assert session["claude_key_available"] is True
    assert session["claude_key"]["hint"] == "…1234"
    assert KEY not in client.get("/auth/session", headers=_bearer(token)).text


def test_a_key_anthropic_rejects_is_not_saved(client, anthropic):
    user_id, token = _sign_up(client)
    anthropic.status = 401

    response = _connect(client, token)

    assert response.status_code == 400
    assert "didn't accept" in response.json()["detail"]
    assert db.get_llm_credential(user_id) is None


@pytest.mark.parametrize("key", ["sk-openai-123456789012345", "sk-ant-short", "sk-ant-has spaces-in-it-123456"])
def test_things_that_are_not_anthropic_keys_are_refused_without_asking_anthropic(client, anthropic, key):
    _, token = _sign_up(client)

    assert _connect(client, token, key).status_code == 400
    assert anthropic.calls == []


def test_disconnecting_removes_the_key(client):
    user_id, token = _sign_up(client)
    _connect(client, token)

    assert client.delete("/account/claude", headers=_bearer(token)).status_code == 204

    assert db.get_llm_credential(user_id) is None
    assert client.get("/account/claude", headers=_bearer(token)).json() is None


def test_deleting_a_user_deletes_their_key(client):
    _, admin = _sign_up(client, "admin@example.com")
    alice_id, alice = _sign_up(client)
    _connect(client, alice)

    client.delete(f"/admin/users/{alice_id}", headers=_bearer(admin))

    assert db.get_llm_credential(alice_id) is None


def test_the_activity_log_never_contains_the_key(client):
    _, admin = _sign_up(client, "admin@example.com")
    _connect(client, admin)
    _connect(client, admin)  # Replace it.
    client.delete("/account/claude", headers=_bearer(admin))

    activity = client.get("/admin/activity", headers=_bearer(admin))

    actions = [e["action"] for e in activity.json()["items"]]
    assert actions[:3] == ["account.claude_disconnected", "account.claude_connected", "account.claude_connected"]
    assert KEY not in activity.text


def test_saving_a_key_needs_a_secret_key(client, monkeypatch):
    _, token = _sign_up(client)
    monkeypatch.setattr(get_settings(), "secret_key", None)

    assert _connect(client, token).status_code == 404
    assert client.get("/auth/session", headers=_bearer(token)).json()["claude_key_available"] is False


# Using the saved key


def _ai_scan(client, token, **llm):
    return client.post(
        "/scan",
        json={"target": "https://github.com/acme/skill", "llm": {"provider": "anthropic", **llm}},
        headers=_bearer(token),
    )


def test_a_scan_can_use_the_saved_key(client):
    _, token = _sign_up(client)
    _connect(client, token)

    response = _ai_scan(client, token, use_saved_key=True, model="claude-sonnet-5")

    assert response.status_code == 200
    job = client.submitted[0]
    assert job.llm.api_key == KEY  # In memory only, for this scan.
    assert db.get_scan(job.id)["llm_model"] == "claude-sonnet-5"


def test_using_a_saved_key_without_one_is_refused(client):
    _, token = _sign_up(client)

    response = _ai_scan(client, token, use_saved_key=True)

    assert response.status_code == 400
    assert "account page" in response.json()["detail"]


def test_one_user_never_gets_another_users_key(client):
    _, alice = _sign_up(client)
    _connect(client, alice)
    _, bob = _sign_up(client, "bob@example.com")

    assert _ai_scan(client, bob, use_saved_key=True).status_code == 400


def test_validation_errors_do_not_echo_the_key(client):
    _, token = _sign_up(client)

    response = client.post(
        "/scan",
        json={"target": "https://github.com/acme/skill", "llm": {"provider": "not-a-provider", "api_key": KEY}},
        headers=_bearer(token),
    )

    assert response.status_code == 422
    assert KEY not in response.text


def test_a_server_can_offer_claude_only_and_no_custom_urls(client, monkeypatch):
    _, token = _sign_up(client)
    monkeypatch.setattr(get_settings(), "ai_providers", ["anthropic"])
    monkeypatch.setattr(get_settings(), "allow_custom_ai_url", False)

    assert _ai_scan(client, token, api_key=KEY).status_code == 200
    openai = client.post(
        "/scan",
        json={"target": "https://github.com/acme/skill", "llm": {"provider": "openai", "api_key": "sk-x"}},
        headers=_bearer(token),
    )
    assert openai.status_code == 422
    assert _ai_scan(client, token, api_key=KEY, base_url="http://169.254.169.254/").status_code == 422
    health = client.get("/health").json()
    assert (health["ai_providers"], health["allow_custom_ai_url"]) == (["anthropic"], False)


def test_a_server_can_turn_off_the_shared_claude_login(client, monkeypatch):
    _, admin = _sign_up(client, "admin@example.com")
    monkeypatch.setattr(get_settings(), "claude_cli", False)

    assert client.post("/admin/claude-login/start", headers=_bearer(admin)).status_code == 404
    assert client.get("/health").json()["claude_cli_available"] is False
    assert "claude_cli" not in client.get("/health").json()["ai_providers"]


# Keys held for a scan


def test_deleting_a_scan_deletes_its_held_key(client):
    user_id, _ = _sign_up(client)
    job = scanner.create_job("https://github.com/acme/skill", LLMConfig(provider="anthropic", api_key=KEY), owner_id=user_id)
    claude_key.hold_for_scan(job.id, KEY)

    db.delete_scan(job.id)

    assert db.get_scan_secret(job.id) is None
