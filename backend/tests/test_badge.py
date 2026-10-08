from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth import passwords
from app.core.config import get_settings
from app.main import app

PASSWORD = "correct horse battery"
TARGET = "https://github.com/acme/skill"
UNKNOWN = {"recommendation": None, "risk_score": None, "scanned_at": None, "share_token": None}


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
    monkeypatch.setattr(settings, "daily_scan_quota", None)
    monkeypatch.setattr(settings, "concurrent_scan_quota", None)
    return TestClient(app)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _accounts(client) -> tuple[str, str]:
    """Alice and bob, signed in."""
    admin = client.post("/auth/setup", json={"email": "admin@example.com", "password": PASSWORD}).json()["token"]
    tokens = []
    for email in ("alice@example.com", "bob@example.com"):
        client.post("/admin/users", json={"email": email, "password": PASSWORD}, headers=_bearer(admin))
        tokens.append(client.post("/auth/login", json={"email": email, "password": PASSWORD}).json()["token"])
    return tokens[0], tokens[1]


def _scan(client, session: str, recommendation: str = "SAFE", score: int = 8, target: str = TARGET, **options) -> str:
    scan_id = client.post("/scan", json={"target": target, **options}, headers=_bearer(session)).json()["id"]
    result = {"risk_assessment": {"score": score, "severity": "LOW", "recommendation": recommendation}, "issues": []}
    db.update_scan(id=scan_id, status="done", finished_at=time.time(), result=result, error=None)
    return scan_id


def _share(client, session: str, scan_id: str) -> str:
    return client.post(f"/scan/{scan_id}/share", headers=_bearer(session)).json()["token"]


def test_a_badge_shows_the_shared_result_its_owner_put_on_it(client):
    alice, _ = _accounts(client)
    scan_id = _scan(client, alice, "CAUTION", 41)
    token = _share(client, alice, scan_id)

    assert client.post(f"/scan/{scan_id}/badge", headers=_bearer(alice)).status_code == 204

    badge = client.get("/badge", params={"target": TARGET}).json()
    assert badge["recommendation"] == "CAUTION" and badge["risk_score"] == 41
    assert badge["scanned_at"] == pytest.approx(time.time(), abs=60)
    assert client.get(f"/scan/{scan_id}", headers=_bearer(alice)).json()["badge"] is True
    # Its report link opens the result by a badge link, never the share link, which stays secret.
    assert badge["share_token"] == f"badge-{scan_id}" != token
    assert client.get(f"/shared/{badge['share_token']}").json()["id"] == scan_id
    # Only while it's on the badge.
    client.delete(f"/scan/{scan_id}/badge", headers=_bearer(alice))
    assert client.get(f"/shared/badge-{scan_id}").status_code == 404


def test_a_private_or_only_shared_scan_never_shows(client):
    alice, _ = _accounts(client)
    private = _scan(client, alice, "DO_NOT_INSTALL", 90)
    assert client.get("/badge", params={"target": TARGET}).json() == UNKNOWN
    # Shared by link, but not put on the badge.
    _share(client, alice, private)
    assert client.get("/badge", params={"target": TARGET}).json() == UNKNOWN
    # Only a shared result can be.
    other = _scan(client, alice)
    assert client.post(f"/scan/{other}/badge", headers=_bearer(alice)).status_code == 409


def test_revoking_the_link_takes_the_result_off_the_badge(client):
    alice, _ = _accounts(client)
    scan_id = _scan(client, alice)
    _share(client, alice, scan_id)
    client.post(f"/scan/{scan_id}/badge", headers=_bearer(alice))

    client.delete(f"/scan/{scan_id}/share", headers=_bearer(alice))

    assert client.get("/badge", params={"target": TARGET}).json() == UNKNOWN
    # Sharing again doesn't put it back.
    _share(client, alice, scan_id)
    assert client.get("/badge", params={"target": TARGET}).json() == UNKNOWN


def test_the_badge_shows_the_latest_scan_on_it_and_falls_back_when_its_removed(client):
    alice, bob = _accounts(client)
    first = _scan(client, alice, "SAFE", 5)
    _share(client, alice, first)
    client.post(f"/scan/{first}/badge", headers=_bearer(alice))
    later = _scan(client, bob, "DO_NOT_INSTALL", 88)
    _share(client, bob, later)
    client.post(f"/scan/{later}/badge", headers=_bearer(bob))

    assert client.get("/badge", params={"target": TARGET}).json()["recommendation"] == "DO_NOT_INSTALL"

    assert client.delete(f"/scan/{later}/badge", headers=_bearer(bob)).status_code == 204
    assert client.get("/badge", params={"target": TARGET}).json()["recommendation"] == "SAFE"


def test_only_the_owner_puts_a_scan_on_the_badge(client):
    alice, bob = _accounts(client)
    scan_id = _scan(client, alice)
    _share(client, alice, scan_id)

    assert client.post(f"/scan/{scan_id}/badge", headers=_bearer(bob)).status_code == 404
    assert client.post(f"/scan/{scan_id}/badge").status_code == 401
    assert client.get("/badge", params={"target": TARGET}).json() == UNKNOWN


def test_a_scan_with_a_baseline_cant_be_on_a_badge(client):
    # Its accepted findings don't count, so it would read safer than the skill is.
    alice, _ = _accounts(client)
    scan_id = _scan(client, alice, baseline='version: 2\nrules:\n  - id: "TR3"\n    reason: "Accepted"\n')
    _share(client, alice, scan_id)

    refused = client.post(f"/scan/{scan_id}/badge", headers=_bearer(alice))

    assert refused.status_code == 422 and "baseline" in refused.json()["detail"]


def test_a_scan_the_skills_own_baseline_applied_to_cant_be_on_a_badge(client):
    alice, _ = _accounts(client)
    scan_id = _scan(client, alice, use_shipped_baseline=True)
    result = db.get_scan(scan_id)["result"]
    db.update_scan(id=scan_id, status="done", finished_at=time.time(), result={**result, "applied_baseline": "shipped"}, error=None)
    _share(client, alice, scan_id)

    refused = client.post(f"/scan/{scan_id}/badge", headers=_bearer(alice))

    assert refused.status_code == 422 and "baseline" in refused.json()["detail"]


def test_a_file_link_finds_its_badge_as_the_scan_stored_it(client):
    alice, _ = _accounts(client)
    blob = "https://github.com/acme/skills/blob/main/pdf/SKILL.md"
    scan_id = _scan(client, alice, target=blob)
    _share(client, alice, scan_id)
    client.post(f"/scan/{scan_id}/badge", headers=_bearer(alice))

    # Stored as the raw file; the README's link is the one the user scanned.
    assert db.get_scan(scan_id)["target"].startswith("https://raw.githubusercontent.com/")
    assert client.get("/badge", params={"target": blob}).json()["recommendation"] == "SAFE"


def test_putting_a_scan_on_the_badge_is_in_the_activity_log(client):
    alice, _ = _accounts(client)
    scan_id = _scan(client, alice)
    _share(client, alice, scan_id)
    client.post(f"/scan/{scan_id}/badge", headers=_bearer(alice))
    client.delete(f"/scan/{scan_id}/badge", headers=_bearer(alice))

    entries, _ = db.list_audit(10, 0)
    actions = [entry["action"] for entry in entries]
    assert "scan.badge_added" in actions and "scan.badge_removed" in actions
