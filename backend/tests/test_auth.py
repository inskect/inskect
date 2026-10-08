from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app import auth, db, monitoring
from app.auth import login_throttle, passwords
from app.core.config import Settings, get_settings
from app.main import app

PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def _fast_hashing(monkeypatch):
    # Real-strength scrypt takes ~0.3 s a hash; these tests hash dozens of times.
    monkeypatch.setattr(passwords, "_N", 2**10)
    passwords.dummy_hash.cache_clear()
    yield
    passwords.dummy_hash.cache_clear()


@pytest.fixture
def client(temp_db, fake_runner, monkeypatch):
    monkeypatch.setattr(get_settings(), "auth", "accounts")
    monkeypatch.setattr(get_settings(), "allow_signup", None)
    return TestClient(app)


@pytest.fixture
def open_client(temp_db, fake_runner, monkeypatch):
    monkeypatch.setattr(get_settings(), "auth", "none")
    return TestClient(app)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _setup_admin(client) -> str:
    response = client.post("/auth/setup", json={"email": "Admin@Example.com", "password": PASSWORD})
    assert response.status_code == 200
    return response.json()["token"]


def _add_user(client, admin: str, email: str, role: str = "user") -> str:
    response = client.post("/admin/users", json={"email": email, "password": PASSWORD, "role": role}, headers=_bearer(admin))
    assert response.status_code == 201
    login = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200
    return login.json()["token"]


def _scan(client, token: str) -> str:
    response = client.post("/scan", json={"target": "https://github.com/acme/skill"}, headers=_bearer(token))
    assert response.status_code == 200
    return response.json()["id"]


# Without accounts


def test_without_accounts_everything_is_open(open_client):
    session = open_client.get("/auth/session").json()
    session.pop("features")
    assert session == {"auth": "none", "user": None, "needs_setup": False, "signup_allowed": False, "email_enabled": False, "claude_key_available": False, "claude_key": None}

    scan_id = open_client.post("/scan", json={"target": "https://github.com/acme/skill"}).json()["id"]
    assert open_client.get(f"/scan/{scan_id}").status_code == 200
    assert open_client.put("/settings", json={"scan_retention_days": 3}).status_code == 200


def test_without_accounts_account_routes_are_off(open_client):
    assert open_client.post("/auth/login", json={"email": "a@b.c", "password": PASSWORD}).status_code == 404
    assert open_client.post("/auth/setup", json={"email": "a@b.c", "password": PASSWORD}).status_code == 404
    assert open_client.get("/admin/users").status_code == 404


def test_no_admin_token_is_checked_any_more(open_client, monkeypatch):
    monkeypatch.setenv("INSKECT_ADMIN_TOKEN", "left-over")

    assert open_client.put("/settings", json={"scan_retention_days": 3}).status_code == 200


# First-run setup and sign-in


def test_a_fresh_server_asks_for_its_first_admin(client):
    session = client.get("/auth/session").json()
    session.pop("features")
    assert session == {
        "auth": "accounts",
        "user": None,
        "needs_setup": True,
        "signup_allowed": True,
        "email_enabled": False,
        "claude_key_available": False,
        "claude_key": None,
    }

    token = _setup_admin(client)

    session = client.get("/auth/session", headers=_bearer(token)).json()
    assert session["needs_setup"] is False
    assert session["user"]["email"] == "admin@example.com"
    assert session["user"]["role"] == "admin"


def test_setup_only_works_once(client):
    _setup_admin(client)

    response = client.post("/auth/setup", json={"email": "intruder@example.com", "password": PASSWORD})

    assert response.status_code == 409
    assert db.count_users() == 1


def test_sign_in_and_out(client):
    _setup_admin(client)

    token = client.post("/auth/login", json={"email": " ADMIN@example.com ", "password": PASSWORD}).json()["token"]
    assert client.get("/scan", headers=_bearer(token)).status_code == 200

    assert client.post("/auth/logout", headers=_bearer(token)).status_code == 204
    assert client.get("/scan", headers=_bearer(token)).status_code == 401


@pytest.mark.parametrize(("email", "password"), [("admin@example.com", "wrong password"), ("nobody@example.com", PASSWORD)])
def test_wrong_credentials_get_the_same_answer(client, email, password):
    _setup_admin(client)

    response = client.post("/auth/login", json={"email": email, "password": password})

    assert response.status_code == 401
    assert response.json()["detail"] == "Wrong email or password"


def test_sign_in_attempts_are_rate_limited(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "login_rate_limit", 2)
    for _ in range(2):
        client.post("/auth/login", json={"email": "a@b.c", "password": "x" * 12})

    assert client.post("/auth/login", json={"email": "a@b.c", "password": "x" * 12}).status_code == 429


@pytest.fixture
def throttled(client, monkeypatch):
    """Three failed sign-ins per account; the per-address limit out of the way; alerts caught."""
    monkeypatch.setattr(login_throttle, "TIERS", ((3, 900),))
    monkeypatch.setattr(get_settings(), "login_rate_limit", 1000)
    alerts = []
    monkeypatch.setattr(monitoring, "send_alert", lambda title, text, settings=None: alerts.append(title) or ["webhook"])
    return alerts


def _login(client, email: str, password: str, address: str):
    return client.post("/auth/login", json={"email": email, "password": password}, headers={"X-Forwarded-For": address})


def test_failed_sign_ins_on_one_account_are_slowed_from_any_address(client, throttled):
    _setup_admin(client)
    for i in range(3):
        assert _login(client, "admin@example.com", "wrong password!", f"203.0.113.{i}").status_code == 401

    # From yet another address, and even with the right password.
    response = _login(client, "ADMIN@example.com", PASSWORD, "198.51.100.7")

    assert response.status_code == 429
    assert response.json()["detail"].startswith("Too many failed sign-ins with this email")
    assert int(response.headers["Retry-After"]) > 0
    # Other accounts aren't affected.
    assert _login(client, "nobody@example.com", PASSWORD, "198.51.100.7").status_code == 401


def test_the_limit_doesnt_tell_which_emails_have_an_account(client, throttled):
    _setup_admin(client)
    answers = []
    for email in ("admin@example.com", "nobody@example.com"):
        for i in range(3):
            _login(client, email, "wrong password!", f"203.0.113.{i}")
        response = _login(client, email, "wrong password!", "198.51.100.7")
        answers.append((response.status_code, response.json()["detail"]))

    assert answers[0] == answers[1]


def test_successful_sign_ins_dont_count_toward_the_limit(client, throttled):
    _setup_admin(client)
    _login(client, "admin@example.com", "wrong password!", "203.0.113.1")
    for _ in range(5):
        assert _login(client, "admin@example.com", PASSWORD, "203.0.113.1").status_code == 200
    _login(client, "admin@example.com", "wrong password!", "203.0.113.1")

    assert _login(client, "admin@example.com", PASSWORD, "203.0.113.1").status_code == 200


def test_hitting_the_limit_alerts_and_is_logged_on_the_account(client, throttled):
    admin = _setup_admin(client)
    for i in range(6):
        _login(client, "admin@example.com", "wrong password!", f"203.0.113.{i}")

    assert throttled == [monitoring.LOCKOUT_RULE.title]
    assert db.monitor_counts(since=0)[monitoring.SIGN_IN_LOCKED] == 1
    activity = client.get("/admin/activity", headers=_bearer(admin)).json()["items"]
    locked = [e for e in activity if e["action"] == "sign_in.locked"]
    assert [(e["actor_id"], e["target_email"]) for e in locked] == [(None, "admin@example.com")]


def test_weak_passwords_and_bad_emails_are_refused(client):
    assert client.post("/auth/setup", json={"email": "admin@example.com", "password": "short"}).status_code == 400
    assert client.post("/auth/setup", json={"email": "not-an-email", "password": PASSWORD}).status_code == 400
    assert db.count_users() == 0


def test_an_expired_session_is_refused(client, monkeypatch):
    token = _setup_admin(client)
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + get_settings().session_days * 86400 + 1)

    assert client.get("/scan", headers=_bearer(token)).status_code == 401


def test_only_session_hashes_are_stored(client):
    token = _setup_admin(client)

    assert db.get_session_user(token, now=time.time()) is None  # The raw token isn't a key.
    assert auth.user_for_token(token) is not None


# Signed-in access


def test_every_scan_route_needs_a_session_with_accounts(client):
    _setup_admin(client)

    assert client.post("/scan", json={"target": "https://github.com/acme/skill"}).status_code == 401
    assert client.get("/scan").status_code == 401
    assert client.get("/scan/anything").status_code == 401
    assert client.get("/scan/anything/logs").status_code == 401
    assert client.delete("/scan/anything").status_code == 401
    assert client.put("/settings", json={"scan_retention_days": 3}).status_code == 401
    assert client.post("/admin/claude-login/start").status_code == 401


def test_users_only_see_and_delete_their_own_scans(client):
    admin = _setup_admin(client)
    alice = _add_user(client, admin, "alice@example.com")
    bob = _add_user(client, admin, "bob@example.com")
    alices_scan = _scan(client, alice)

    assert [s["id"] for s in client.get("/scan", headers=_bearer(alice)).json()["items"]] == [alices_scan]
    assert client.get("/scan", headers=_bearer(bob)).json() == {"items": [], "total": 0}
    for method, path in [("get", f"/scan/{alices_scan}"), ("get", f"/scan/{alices_scan}/logs"), ("delete", f"/scan/{alices_scan}")]:
        assert getattr(client, method)(path, headers=_bearer(bob)).status_code == 404
    assert db.get_scan(alices_scan) is not None

    assert client.delete(f"/scan/{alices_scan}", headers=_bearer(alice)).status_code == 204


def test_admins_see_every_scan_including_ones_from_before_accounts(client):
    db.insert_scan(id="legacy", target="t", status="done", created_at=1.0, provider=None)
    admin = _setup_admin(client)
    alice = _add_user(client, admin, "alice@example.com")
    alices_scan = _scan(client, alice)

    ids = {s["id"] for s in client.get("/scan", headers=_bearer(admin)).json()["items"]}
    assert ids == {"legacy", alices_scan}
    assert client.get("/scan/legacy", headers=_bearer(alice)).status_code == 404


def test_only_admins_manage_the_server(client):
    admin = _setup_admin(client)
    alice = _add_user(client, admin, "alice@example.com")

    assert client.put("/settings", json={"scan_retention_days": 3}, headers=_bearer(alice)).status_code == 403
    assert client.post("/admin/claude-login/start", headers=_bearer(alice)).status_code == 403
    assert client.get("/admin/users", headers=_bearer(alice)).status_code == 403
    assert client.post("/admin/users", json={"email": "x@y.z", "password": PASSWORD}, headers=_bearer(alice)).status_code == 403
    assert client.put("/settings", json={"scan_retention_days": 3}, headers=_bearer(admin)).status_code == 200


# Managing users


def test_admins_add_list_and_remove_users(client):
    admin = _setup_admin(client)
    alice = _add_user(client, admin, "alice@example.com")
    alice_id = client.get("/auth/session", headers=_bearer(alice)).json()["user"]["id"]

    users = client.get("/admin/users", headers=_bearer(admin)).json()
    assert [(u["email"], u["role"]) for u in users] == [("admin@example.com", "admin"), ("alice@example.com", "user")]
    assert "password_hash" not in users[0]

    assert client.delete(f"/admin/users/{alice_id}", headers=_bearer(admin)).status_code == 204
    assert client.get("/scan", headers=_bearer(alice)).status_code == 401  # Their sessions end too.


def test_duplicate_emails_are_refused(client):
    admin = _setup_admin(client)
    _add_user(client, admin, "alice@example.com")

    response = client.post("/admin/users", json={"email": "ALICE@example.com", "password": PASSWORD}, headers=_bearer(admin))

    assert response.status_code == 409


def test_admins_cannot_lock_themselves_out(client):
    admin = _setup_admin(client)
    admin_id = client.get("/auth/session", headers=_bearer(admin)).json()["user"]["id"]

    assert client.delete(f"/admin/users/{admin_id}", headers=_bearer(admin)).status_code == 409


def test_the_last_admin_cannot_be_removed(client):
    admin = _setup_admin(client)
    other_admin = _add_user(client, admin, "second@example.com", role="admin")
    first_id = client.get("/auth/session", headers=_bearer(admin)).json()["user"]["id"]
    second_id = client.get("/auth/session", headers=_bearer(other_admin)).json()["user"]["id"]

    assert client.delete(f"/admin/users/{second_id}", headers=_bearer(admin)).status_code == 204
    _add_user(client, admin, "third@example.com", role="admin")
    assert client.delete(f"/admin/users/{first_id}", headers=_bearer(admin)).status_code == 409  # Self.


# Deleting an account


def test_a_user_deletes_their_account_and_everything_of_theirs(client):
    admin = _setup_admin(client)
    alice = _add_user(client, admin, "alice@example.com")
    alice_id = client.get("/auth/session", headers=_bearer(alice)).json()["user"]["id"]
    scan_id = _scan(client, alice)
    client.post(f"/scan/{scan_id}/share", headers=_bearer(alice))
    reset_token, _ = auth.issue_password_reset(alice_id)
    kept = _scan(client, admin)

    assert client.request("DELETE", "/account", json={"password": "wrong password!"}, headers=_bearer(alice)).status_code == 403
    assert client.request("DELETE", "/account", json={"password": PASSWORD}, headers=_bearer(alice)).status_code == 204

    assert db.get_user(alice_id) is None
    assert db.get_scan(scan_id) is None and db.get_scan(kept) is not None
    assert client.get("/scan", headers=_bearer(alice)).status_code == 401
    with pytest.raises(auth.AuthError):
        auth.reset_password(reset_token, "a new password")
    entries = db.list_audit(100, 0)[0]
    mentioning = [e for e in entries if alice_id in (e["actor_id"], e["target_id"])]
    assert mentioning and all(e["actor_email"] != "alice@example.com" and e["target_email"] is None for e in mentioning)
    assert all("alice" not in str(e.get("detail")) for e in mentioning)
    assert entries[0]["action"] == "account.deleted" and entries[0]["actor_id"] is None


def test_the_last_admin_cant_delete_their_account(client):
    admin = _setup_admin(client)

    refused = client.request("DELETE", "/account", json={"password": PASSWORD}, headers=_bearer(admin))

    assert refused.status_code == 409 and "admin" in refused.json()["detail"]


def test_old_activity_and_expired_reset_links_are_pruned(client):
    admin = _setup_admin(client)
    old = time.time() - 400 * 86400
    db.add_audit(created_at=old, actor_id=None, actor_email=None, action="settings.scans_paused", target_id=None, target_email=None, detail=None)

    from app import retention

    retention.sweep_once()

    actions = [e["action"] for e in client.get("/admin/activity", headers=_bearer(admin)).json()["items"]]
    assert "settings.scans_paused" not in actions and "account.created" in actions


# Sign-up


def test_sign_up_can_be_turned_off(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "allow_signup", False)
    _setup_admin(client)

    response = client.post("/auth/signup", json={"email": "new@example.com", "password": PASSWORD})

    assert response.status_code == 403


def test_sign_up_when_allowed(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "allow_signup", True)
    _setup_admin(client)

    response = client.post("/auth/signup", json={"email": "new@example.com", "password": PASSWORD})

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "user"


def test_without_email_sign_up_refuses_a_taken_address(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "allow_signup", True)
    _setup_admin(client)

    response = client.post("/auth/signup", json={"email": "admin@example.com", "password": PASSWORD})

    assert response.status_code == 409


def _emailed_link(message) -> str:
    body = message.get_payload(decode=True).decode()
    return next(line for line in body.splitlines() if line.startswith("https://"))


def test_with_email_sign_up_finishes_from_the_emailed_link(client, smtp):
    _setup_admin(client)

    response = client.post("/auth/signup", json={"email": "New@Example.com", "password": PASSWORD})

    assert response.status_code == 202
    assert response.json() == {"pending": True}
    assert db.get_user_by_email("new@example.com") is None
    assert [m["To"] for m in smtp] == ["new@example.com"]
    link = _emailed_link(smtp[0])
    assert link.startswith("https://inskect.example.com/confirm-signup?token=")
    token = link.split("token=")[1]

    confirmed = client.post("/auth/confirm-signup", json={"token": token})

    assert confirmed.status_code == 200
    assert confirmed.json()["user"]["email"] == "new@example.com"
    assert client.post("/auth/login", json={"email": "new@example.com", "password": PASSWORD}).status_code == 200
    assert client.post("/auth/confirm-signup", json={"token": token}).status_code == 400


def test_with_email_sign_up_answers_the_same_for_a_taken_address(client, smtp):
    _setup_admin(client)
    new = client.post("/auth/signup", json={"email": "new@example.com", "password": PASSWORD})

    taken = client.post("/auth/signup", json={"email": "admin@example.com", "password": "another password"})

    assert (taken.status_code, taken.json()) == (new.status_code, new.json())
    message = smtp[1]
    assert message["To"] == "admin@example.com"
    assert message["Subject"] == "You already have an Inskect account"
    assert "confirm-signup" not in message.get_payload(decode=True).decode()
    # The password sent with it changed nothing.
    assert client.post("/auth/login", json={"email": "admin@example.com", "password": PASSWORD}).status_code == 200


def test_sign_up_emails_to_one_address_are_capped(client, smtp):
    _setup_admin(client)
    for _ in range(auth.SIGNUP_EMAILS_PER_HOUR + 2):
        assert client.post("/auth/signup", json={"email": "new@example.com", "password": PASSWORD}).status_code == 202

    assert len(smtp) == auth.SIGNUP_EMAILS_PER_HOUR


def test_with_email_sign_up_still_checks_the_password(client, smtp):
    _setup_admin(client)

    assert client.post("/auth/signup", json={"email": "new@example.com", "password": "short"}).status_code == 400
    assert smtp == []


def test_a_sign_up_link_cant_be_used_once_sign_up_is_closed(client, smtp, monkeypatch):
    _setup_admin(client)
    client.post("/auth/signup", json={"email": "new@example.com", "password": PASSWORD})
    token = _emailed_link(smtp[0]).split("token=")[1]
    monkeypatch.setattr(get_settings(), "allow_signup", False)

    assert client.post("/auth/confirm-signup", json={"token": token}).status_code == 403


# Auth settings


@pytest.mark.parametrize(
    ("auth_setting", "signup", "expected_auth", "expected_signup"),
    [
        ("none", None, "none", False),
        ("accounts", None, "accounts", True),
        ("accounts", False, "accounts", False),
    ],
)
def test_auth_and_signup_follow_the_settings(temp_db, auth_setting, signup, expected_auth, expected_signup):
    settings = Settings(_env_file=None, auth=auth_setting, allow_signup=signup)

    assert auth.auth_mode(settings) == expected_auth
    assert auth.signup_allowed(settings) is expected_signup


def test_passwords_hash_and_verify():
    encoded = passwords.hash_password(PASSWORD)

    assert encoded.startswith("scrypt$")
    assert PASSWORD not in encoded
    assert passwords.verify_password(PASSWORD, encoded)
    assert not passwords.verify_password("something else", encoded)
    assert not passwords.verify_password(PASSWORD, "garbage")


# Password reset and change


def _user_id(client, token: str) -> str:
    return client.get("/auth/session", headers=_bearer(token)).json()["user"]["id"]


def _reset_link(client, admin: str, user_id: str) -> str:
    response = client.post(f"/admin/users/{user_id}/reset", headers=_bearer(admin))
    assert response.status_code == 200
    path = response.json()["path"]
    assert path.startswith("/reset-password?token=")
    return path.split("token=", 1)[1]


def test_a_reset_link_sets_a_new_password_and_signs_out_elsewhere(client):
    admin = _setup_admin(client)
    alice = _add_user(client, admin, "alice@example.com")
    token = _reset_link(client, admin, _user_id(client, alice))

    response = client.post("/auth/reset", json={"token": token, "password": "a brand new password"})

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "alice@example.com"
    assert client.get("/scan", headers=_bearer(alice)).status_code == 401  # Old session ended.
    assert client.post("/auth/login", json={"email": "alice@example.com", "password": PASSWORD}).status_code == 401
    assert client.post("/auth/login", json={"email": "alice@example.com", "password": "a brand new password"}).status_code == 200


def test_a_reset_link_works_once(client):
    admin = _setup_admin(client)
    token = _reset_link(client, admin, _user_id(client, admin))

    assert client.post("/auth/reset", json={"token": token, "password": "first new password"}).status_code == 200
    again = client.post("/auth/reset", json={"token": token, "password": "second new password"})

    assert again.status_code == 400
    assert "already used" in again.json()["detail"]


def test_a_new_reset_link_cancels_the_previous_one(client):
    admin = _setup_admin(client)
    user_id = _user_id(client, admin)
    first = _reset_link(client, admin, user_id)
    second = _reset_link(client, admin, user_id)

    assert client.post("/auth/reset", json={"token": first, "password": "a brand new password"}).status_code == 400
    assert client.post("/auth/reset", json={"token": second, "password": "a brand new password"}).status_code == 200


def test_an_expired_reset_link_is_refused(client, monkeypatch):
    admin = _setup_admin(client)
    token = _reset_link(client, admin, _user_id(client, admin))
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + auth.RESET_LINK_HOURS * 3600 + 1)

    assert client.post("/auth/reset", json={"token": token, "password": "a brand new password"}).status_code == 400


def test_a_reset_needs_a_strong_password_and_keeps_the_link_usable(client):
    admin = _setup_admin(client)
    token = _reset_link(client, admin, _user_id(client, admin))

    assert client.post("/auth/reset", json={"token": token, "password": "short"}).status_code == 400
    assert client.post("/auth/reset", json={"token": token, "password": "a brand new password"}).status_code == 200


def test_only_admins_issue_reset_links(client):
    admin = _setup_admin(client)
    alice = _add_user(client, admin, "alice@example.com")

    assert client.post(f"/admin/users/{_user_id(client, admin)}/reset", headers=_bearer(alice)).status_code == 403
    assert client.post("/admin/users/nobody/reset", headers=_bearer(admin)).status_code == 404


def test_reset_links_are_stored_hashed(client):
    admin = _setup_admin(client)
    token = _reset_link(client, admin, _user_id(client, admin))

    assert db.consume_password_reset(token, now=time.time()) is None  # The raw token isn't a key.


def test_changing_your_password_keeps_this_session_and_ends_the_others(client):
    admin = _setup_admin(client)
    other_device = client.post("/auth/login", json={"email": "admin@example.com", "password": PASSWORD}).json()["token"]

    response = client.post(
        "/auth/password",
        json={"current_password": PASSWORD, "new_password": "a brand new password"},
        headers=_bearer(admin),
    )

    assert response.status_code == 204
    assert client.get("/scan", headers=_bearer(admin)).status_code == 200
    assert client.get("/scan", headers=_bearer(other_device)).status_code == 401
    assert client.post("/auth/login", json={"email": "admin@example.com", "password": "a brand new password"}).status_code == 200


def test_changing_your_password_needs_the_current_one(client):
    admin = _setup_admin(client)

    response = client.post(
        "/auth/password",
        json={"current_password": "not my password", "new_password": "a brand new password"},
        headers=_bearer(admin),
    )

    assert response.status_code == 400
    assert client.post("/auth/password", json={"current_password": PASSWORD, "new_password": "x"}).status_code == 401


def test_the_lockout_command_prints_a_working_link(client, capsys):
    from app.auth import reset_link

    _setup_admin(client)

    assert reset_link.main(["reset_link", "Admin@Example.com"]) == 0
    path = capsys.readouterr().out.strip().splitlines()[-1]
    token = path.split("token=", 1)[1]
    assert client.post("/auth/reset", json={"token": token, "password": "a brand new password"}).status_code == 200
    assert reset_link.main(["reset_link", "nobody@example.com"]) == 1


def test_the_session_says_what_this_server_offers(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "daily_scan_quota", 7)
    monkeypatch.setattr(settings, "concurrent_scan_quota", 0)

    features = client.get("/auth/session").json()["features"]

    # Uploads to the local store, no GitHub App: 7 scans a day, no limit at once.
    assert features == {"uploads": True, "github": False, "daily_quota": 7, "concurrent_quota": None}
