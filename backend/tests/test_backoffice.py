from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth import passwords
from app.core.config import get_settings
from app.main import app

PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def _fast_hashing(monkeypatch):
    monkeypatch.setattr(passwords, "_N", 2**10)
    passwords.dummy_hash.cache_clear()
    yield
    passwords.dummy_hash.cache_clear()


@pytest.fixture
def client(temp_db, fake_runner, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "auth", "accounts")
    monkeypatch.setattr(settings, "allow_signup", None)
    for field in ("smtp_host", "mail_from", "public_url"):
        monkeypatch.setattr(settings, field, None)
    return TestClient(app)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin(client) -> str:
    return client.post("/auth/setup", json={"email": "admin@example.com", "password": PASSWORD}).json()["token"]


def _user(client, admin: str, email_address: str = "alice@example.com", role: str = "user") -> tuple[str, str]:
    created = client.post(
        "/admin/users", json={"email": email_address, "password": PASSWORD, "role": role}, headers=_bearer(admin)
    ).json()
    token = client.post("/auth/login", json={"email": email_address, "password": PASSWORD}).json()["token"]
    return created["id"], token


def _patch(client, admin: str, user_id: str, **changes):
    return client.patch(f"/admin/users/{user_id}", json=changes, headers=_bearer(admin))


# Suspension


def test_a_suspended_user_is_signed_out_and_cannot_sign_back_in(client):
    admin = _admin(client)
    alice_id, alice = _user(client, admin)

    assert _patch(client, admin, alice_id, status="suspended").json()["status"] == "suspended"

    assert client.get("/scan", headers=_bearer(alice)).status_code == 401
    login = client.post("/auth/login", json={"email": "alice@example.com", "password": PASSWORD})
    assert login.status_code == 403
    assert "suspended" in login.json()["detail"]

    _patch(client, admin, alice_id, status="active")
    assert client.post("/auth/login", json={"email": "alice@example.com", "password": PASSWORD}).status_code == 200


def test_a_suspended_user_cannot_use_a_reset_link(client):
    admin = _admin(client)
    alice_id, _ = _user(client, admin)
    token = client.post(f"/admin/users/{alice_id}/reset", headers=_bearer(admin)).json()["path"].split("token=")[1]
    _patch(client, admin, alice_id, status="suspended")

    assert client.post("/auth/reset", json={"token": token, "password": "a brand new password"}).status_code == 403


def test_a_wrong_password_on_a_suspended_account_says_nothing_about_it(client):
    admin = _admin(client)
    alice_id, _ = _user(client, admin)
    _patch(client, admin, alice_id, status="suspended")

    response = client.post("/auth/login", json={"email": "alice@example.com", "password": "wrong password!"})

    assert response.status_code == 401
    assert "suspended" not in response.json()["detail"]


# Roles and guards


def test_promoting_a_user_gives_them_the_backoffice(client):
    admin = _admin(client)
    alice_id, alice = _user(client, admin)
    assert client.get("/admin/overview", headers=_bearer(alice)).status_code == 403

    assert _patch(client, admin, alice_id, role="admin").json()["role"] == "admin"

    assert client.get("/admin/overview", headers=_bearer(alice)).status_code == 200


def test_admins_cannot_demote_or_suspend_themselves(client):
    admin = _admin(client)
    admin_id = client.get("/auth/session", headers=_bearer(admin)).json()["user"]["id"]

    assert _patch(client, admin, admin_id, role="user").status_code == 409
    assert _patch(client, admin, admin_id, status="suspended").status_code == 409


def test_there_is_always_an_active_admin(client):
    admin = _admin(client)
    admin_id = client.get("/auth/session", headers=_bearer(admin)).json()["user"]["id"]
    second_id, second = _user(client, admin, "second@example.com", role="admin")

    assert _patch(client, second, admin_id, status="suspended").status_code == 200
    # `second` is now the only active admin, so nobody can take that away, not even another admin.
    assert _patch(client, second, second_id, role="user").status_code == 409
    third_id, _ = _user(client, second, "third@example.com", role="admin")
    assert _patch(client, second, third_id, role="user").status_code == 200


# Directory and detail


def test_the_directory_shows_status_scans_and_last_sign_in(client):
    admin = _admin(client)
    _, alice = _user(client, admin)
    client.post("/scan", json={"target": "https://github.com/acme/skill"}, headers=_bearer(alice))

    users = {u["email"]: u for u in client.get("/admin/users", headers=_bearer(admin)).json()}

    assert users["alice@example.com"]["scan_count"] == 1
    assert users["alice@example.com"]["status"] == "active"
    assert users["alice@example.com"]["last_login_at"] is not None
    assert "password_hash" not in users["alice@example.com"]
    found = client.get("/admin/users", params={"query": "ALI"}, headers=_bearer(admin)).json()
    assert [u["email"] for u in found] == ["alice@example.com"]


def test_a_user_page_shows_their_recent_scans_and_history(client):
    admin = _admin(client)
    alice_id, alice = _user(client, admin)
    scan_id = client.post("/scan", json={"target": "https://github.com/acme/skill"}, headers=_bearer(alice)).json()["id"]
    _patch(client, admin, alice_id, role="admin")

    detail = client.get(f"/admin/users/{alice_id}", headers=_bearer(admin)).json()

    assert detail["user"]["email"] == "alice@example.com"
    assert [(s["id"], s["report_no"]) for s in detail["recent_scans"]] == [(scan_id, 1)]
    assert [a["action"] for a in detail["activity"]] == ["user.role_changed", "account.created"]
    assert detail["activity"][0]["detail"] == "user → admin"
    assert detail["ai_usage"] == {"days": 30, "scans": 0, "input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}
    assert client.get("/admin/users/nobody", headers=_bearer(admin)).status_code == 404


# Overview and activity


def test_the_overview_counts_users_and_scans(client):
    admin = _admin(client)
    alice_id, _ = _user(client, admin)
    _patch(client, admin, alice_id, status="suspended")
    client.post("/scan", json={"target": "https://github.com/acme/skill"}, headers=_bearer(admin))

    overview = client.get("/admin/overview", headers=_bearer(admin)).json()

    assert overview["users"] == {"total": 2, "admins": 1, "suspended": 1, "new": 2}
    assert overview["scans"]["total"] == 1
    assert overview["scans"]["active"] == 1
    assert overview["email_enabled"] is False
    assert overview["recent_activity"][0]["action"] == "user.suspended"


def test_the_activity_log_records_who_did_what(client):
    admin = _admin(client)
    alice_id, _ = _user(client, admin)
    _patch(client, admin, alice_id, status="suspended")
    client.delete(f"/admin/users/{alice_id}", headers=_bearer(admin))

    page = client.get("/admin/activity", headers=_bearer(admin)).json()

    assert [e["action"] for e in page["items"]] == ["user.deleted", "user.suspended", "account.created", "account.created"]
    assert page["items"][0]["actor_email"] == "admin@example.com"
    # Deleted, alice's entries keep only her id.
    assert {e["target_email"] for e in page["items"][:2]} == {None}
    assert page["items"][1]["target_id"] == alice_id and page["items"][1]["detail"] is None
    assert page["total"] == 4


def test_only_admins_see_the_backoffice(client):
    admin = _admin(client)
    _, alice = _user(client, admin)

    for path in ("/admin/overview", "/admin/activity", "/admin/users"):
        assert client.get(path, headers=_bearer(alice)).status_code == 403
        assert client.get(path).status_code == 401


# Sign-up setting


def test_admins_turn_sign_up_off_and_on(client):
    admin = _admin(client)
    assert client.get("/settings").json()["allow_signup"] is True

    assert client.put("/settings", json={"allow_signup": False}, headers=_bearer(admin)).json()["allow_signup"] is False
    assert client.post("/auth/signup", json={"email": "new@example.com", "password": PASSWORD}).status_code == 403
    assert client.get("/auth/session").json()["signup_allowed"] is False

    client.put("/settings", json={"allow_signup": True}, headers=_bearer(admin))
    assert client.post("/auth/signup", json={"email": "new@example.com", "password": PASSWORD}).status_code == 200
    actions = [e["action"] for e in client.get("/admin/activity", headers=_bearer(admin)).json()["items"]]
    assert actions[:3] == ["account.created", "settings.signup_changed", "settings.signup_changed"]


def test_changing_one_setting_leaves_the_other_alone(client):
    admin = _admin(client)
    client.put("/settings", json={"scan_retention_days": 14}, headers=_bearer(admin))

    settings = client.put("/settings", json={"allow_signup": False}, headers=_bearer(admin)).json()

    assert settings == {"scan_retention_days": 14, "allow_signup": False, "scans_paused": False, "daily_scan_quota": None, "concurrent_scan_quota": None}


# Email


def test_forgot_password_emails_a_working_link(client, smtp):
    _admin(client)
    assert client.get("/auth/session").json()["email_enabled"] is True

    response = client.post("/auth/forgot", json={"email": "Admin@Example.com"})

    assert response.status_code == 202
    assert len(smtp) == 1
    message = smtp[0]
    assert message["To"] == "admin@example.com"
    assert message["From"] == "Inskect <noreply@example.com>"
    body = message.get_payload(decode=True).decode()
    link = next(line for line in body.splitlines() if line.startswith("https://"))
    assert link.startswith("https://inskect.example.com/reset-password?token=")
    token = link.split("token=")[1]
    assert client.post("/auth/reset", json={"token": token, "password": "a brand new password"}).status_code == 200


def test_the_link_host_comes_from_public_url_never_the_request(client, smtp):
    _admin(client)

    client.post("/auth/forgot", json={"email": "admin@example.com"}, headers={"Host": "evil.example", "X-Forwarded-Host": "evil.example"})

    assert "evil.example" not in smtp[0].get_payload(decode=True).decode()


@pytest.mark.parametrize("address", ["nobody@example.com", "not an email"])
def test_forgot_password_answers_the_same_for_unknown_addresses(client, smtp, address):
    _admin(client)

    response = client.post("/auth/forgot", json={"email": address})

    assert response.status_code == 202
    assert response.json() == {"accepted": True}
    assert smtp == []


def test_suspended_accounts_get_no_reset_email(client, smtp):
    admin = _admin(client)
    alice_id, _ = _user(client, admin)
    _patch(client, admin, alice_id, status="suspended")

    client.post("/auth/forgot", json={"email": "alice@example.com"})

    assert smtp == []


def test_without_smtp_there_is_no_email_reset(client):
    admin = _admin(client)
    alice_id, _ = _user(client, admin)

    assert client.get("/auth/session").json()["email_enabled"] is False
    assert client.post("/auth/forgot", json={"email": "alice@example.com"}).status_code == 202
    assert client.post(f"/admin/users/{alice_id}/reset-email", headers=_bearer(admin)).status_code == 409


def test_admins_can_email_a_reset_link(client, smtp):
    admin = _admin(client)
    alice_id, _ = _user(client, admin)

    assert client.post(f"/admin/users/{alice_id}/reset-email", headers=_bearer(admin)).status_code == 204

    assert smtp[0]["To"] == "alice@example.com"
    activity = client.get(f"/admin/users/{alice_id}", headers=_bearer(admin)).json()["activity"]
    assert activity[0]["action"] == "password.reset_email_sent"
    assert activity[0]["actor_email"] == "admin@example.com"


def test_an_unreachable_smtp_server_is_reported_to_the_admin(client, monkeypatch):
    admin = _admin(client)
    alice_id, _ = _user(client, admin)
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "smtp_port", 1)  # Nothing listens there.
    monkeypatch.setattr(settings, "smtp_security", "none")
    monkeypatch.setattr(settings, "mail_from", "noreply@example.com")
    monkeypatch.setattr(settings, "public_url", "https://inskect.example.com")

    response = client.post(f"/admin/users/{alice_id}/reset-email", headers=_bearer(admin))

    assert response.status_code == 502
    # From the sign-in page it fails quietly: the visitor gets the same answer as always.
    assert client.post("/auth/forgot", json={"email": "alice@example.com"}).status_code == 202


def test_the_first_account_is_the_admin_even_through_sign_up(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "allow_signup", False)  # Even with sign-up closed.

    first = client.post("/auth/signup", json={"email": "first@example.com", "password": PASSWORD})
    second = client.post("/auth/signup", json={"email": "second@example.com", "password": PASSWORD})

    assert first.status_code == 200
    assert first.json()["user"]["role"] == "admin"
    assert second.status_code == 403
