from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app import db, quotas
from app.auth import passwords
from app.core.config import get_settings
from app.main import app

PASSWORD = "correct horse battery"
SCAN = {"target": "https://github.com/example/skill"}


@pytest.fixture(autouse=True)
def _fast_hashing(monkeypatch):
    monkeypatch.setattr(passwords, "_N", 2**10)
    passwords.dummy_hash.cache_clear()
    yield
    passwords.dummy_hash.cache_clear()


@pytest.fixture
def settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "daily_scan_quota", None)
    monkeypatch.setattr(settings, "concurrent_scan_quota", None)
    return settings


@pytest.fixture
def client(temp_db, fake_runner, settings, monkeypatch):
    monkeypatch.setattr(settings, "auth", "accounts")
    monkeypatch.setattr(settings, "allow_signup", None)
    # Out of the way: these tests are about quotas, not the per-minute rate limit.
    monkeypatch.setattr(settings, "scan_rate_limit", 1000)
    monkeypatch.setattr(settings, "scan_ip_rate_limit", 1000)
    return TestClient(app)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin(client) -> str:
    return client.post("/auth/setup", json={"email": "admin@example.com", "password": PASSWORD}).json()["token"]


def _user(client, admin: str, email_address: str = "alice@example.com") -> str:
    client.post("/admin/users", json={"email": email_address, "password": PASSWORD}, headers=_bearer(admin))
    return client.post("/auth/login", json={"email": email_address, "password": PASSWORD}).json()["token"]


def _limits(client, admin: str, **changes):
    return client.put("/settings", json=changes, headers=_bearer(admin))


# Storage


def test_scan_limits_are_unset_until_saved(temp_db):
    assert db.get_scan_limits() == {"scans_paused": None, "daily_scan_quota": None, "concurrent_scan_quota": None}

    db.set_scan_limits(scans_paused=True, daily_scan_quota=5, concurrent_scan_quota=0)

    assert db.get_scan_limits() == {"scans_paused": True, "daily_scan_quota": 5, "concurrent_scan_quota": 0}


def test_active_scans_are_counted_per_owner(temp_db):
    db.insert_scan(id="a", target="t", status="running", created_at=1.0, provider=None, owner_id="u1")
    db.insert_scan(id="b", target="t", status="pending", created_at=1.0, provider=None, owner_id="u2")
    db.insert_scan(id="c", target="t", status="done", created_at=1.0, provider=None, owner_id="u1")

    assert db.count_active_scans() == 2
    assert db.count_active_scans(owner_id="u1") == 1


def test_rate_limit_hits_are_counted_within_the_window(temp_db):
    db.rate_limit_hit("k", limit=10, window_seconds=100, now=1000.0)
    db.rate_limit_hit("k", limit=10, window_seconds=100, now=1050.0)
    db.rate_limit_hit("other", limit=10, window_seconds=100, now=1050.0)

    assert db.count_rate_limit_hits("k", window_seconds=100, now=1060.0) == 2
    assert db.count_rate_limit_hits("k", window_seconds=100, now=1120.0) == 1


# Defaults


def test_there_are_no_limits_by_default(temp_db, settings):
    assert quotas.current() == quotas.ScanLimits(paused=False, daily=None, concurrent=None)


def test_configured_quotas_apply_and_zero_means_no_limit(temp_db, settings, monkeypatch):
    monkeypatch.setattr(settings, "daily_scan_quota", 0)
    monkeypatch.setattr(settings, "concurrent_scan_quota", 5)

    assert quotas.current() == quotas.ScanLimits(paused=False, daily=None, concurrent=5)


def test_the_admins_settings_win_over_the_configured_ones(temp_db, settings, monkeypatch):
    monkeypatch.setattr(settings, "daily_scan_quota", 3)
    quotas.save(quotas.ScanLimits(paused=True, daily=None, concurrent=1))

    assert quotas.current() == quotas.ScanLimits(paused=True, daily=None, concurrent=1)


# Enforcement


def test_a_user_is_refused_beyond_the_daily_quota(client, fake_runner):
    admin = _admin(client)
    alice = _user(client, admin)
    _limits(client, admin, daily_scan_quota=2, concurrent_scan_quota=None)

    assert [client.post("/scan", json=SCAN, headers=_bearer(alice)).status_code for _ in range(2)] == [200, 200]
    refused = client.post("/scan", json=SCAN, headers=_bearer(alice))

    assert refused.status_code == 429
    assert "2 inspections for the last 24 hours" in refused.json()["detail"]
    assert "hours" in refused.json()["detail"]
    assert len(fake_runner.submitted) == 2


def test_deleting_scans_does_not_give_quota_back(client):
    admin = _admin(client)
    alice = _user(client, admin)
    _limits(client, admin, daily_scan_quota=1, concurrent_scan_quota=None)

    scan_id = client.post("/scan", json=SCAN, headers=_bearer(alice)).json()["id"]
    assert client.delete(f"/scan/{scan_id}", headers=_bearer(alice)).status_code == 204

    assert client.post("/scan", json=SCAN, headers=_bearer(alice)).status_code == 429


def test_a_user_is_refused_beyond_the_concurrent_quota(client):
    admin = _admin(client)
    alice = _user(client, admin)
    bob = _user(client, admin, "bob@example.com")
    _limits(client, admin, daily_scan_quota=None, concurrent_scan_quota=1)

    assert client.post("/scan", json=SCAN, headers=_bearer(alice)).status_code == 200
    refused = client.post("/scan", json=SCAN, headers=_bearer(alice))

    assert refused.status_code == 429
    assert "1 inspection in progress" in refused.json()["detail"]
    # Counted per user.
    assert client.post("/scan", json=SCAN, headers=_bearer(bob)).status_code == 200


def test_a_scan_refused_for_another_reason_does_not_count(client, fake_runner):
    admin = _admin(client)
    alice = _user(client, admin)
    _limits(client, admin, daily_scan_quota=1, concurrent_scan_quota=None)

    fake_runner.full = True
    assert client.post("/scan", json=SCAN, headers=_bearer(alice)).status_code == 503
    fake_runner.full = False

    assert client.post("/scan", json=SCAN, headers=_bearer(alice)).status_code == 200


def test_admins_have_no_quota(client):
    admin = _admin(client)
    _limits(client, admin, daily_scan_quota=1, concurrent_scan_quota=1)

    assert [client.post("/scan", json=SCAN, headers=_bearer(admin)).status_code for _ in range(3)] == [200] * 3


def test_pausing_refuses_new_scans_for_everyone_until_resumed(client):
    admin = _admin(client)
    alice = _user(client, admin)

    assert _limits(client, admin, scans_paused=True).json()["scans_paused"] is True
    for token in (alice, admin):
        refused = client.post("/scan", json=SCAN, headers=_bearer(token))
        assert refused.status_code == 503
        assert "paused" in refused.json()["detail"]

    _limits(client, admin, scans_paused=False)
    assert client.post("/scan", json=SCAN, headers=_bearer(alice)).status_code == 200


def test_without_accounts_only_the_pause_applies(temp_db, fake_runner, settings, monkeypatch):
    monkeypatch.setattr(settings, "auth", "none")
    quotas.save(quotas.ScanLimits(paused=False, daily=1, concurrent=1))
    client = TestClient(app)

    assert [client.post("/scan", json=SCAN).status_code for _ in range(2)] == [200, 200]
    quotas.save(quotas.ScanLimits(paused=True, daily=1, concurrent=1))
    assert client.post("/scan", json=SCAN).status_code == 503


# Settings and usage


def test_only_admins_change_the_limits_and_each_change_is_audited(client):
    admin = _admin(client)
    alice = _user(client, admin)

    assert _limits(client, alice, scans_paused=True).status_code == 403
    response = _limits(client, admin, scans_paused=True, daily_scan_quota=4, concurrent_scan_quota=None)

    assert response.status_code == 200
    body = response.json()
    assert (body["scans_paused"], body["daily_scan_quota"], body["concurrent_scan_quota"]) == (True, 4, None)
    actions = {entry["action"]: entry["detail"] for entry in client.get("/admin/activity", headers=_bearer(admin)).json()["items"]}
    assert "settings.scans_paused" in actions
    assert actions["settings.quotas_changed"] == "4 a day, no limit at once"


def test_unsent_limits_are_left_alone(client):
    admin = _admin(client)
    _limits(client, admin, daily_scan_quota=4, concurrent_scan_quota=3)

    body = _limits(client, admin, scans_paused=True).json()

    assert (body["daily_scan_quota"], body["concurrent_scan_quota"]) == (4, 3)


@pytest.mark.parametrize("quota", [0, -1])
def test_a_quota_must_be_positive_or_null(client, quota):
    admin = _admin(client)

    assert _limits(client, admin, daily_scan_quota=quota).status_code == 422


def test_usage_shows_what_the_user_has_left(client):
    admin = _admin(client)
    alice = _user(client, admin)
    _limits(client, admin, daily_scan_quota=5, concurrent_scan_quota=2)
    client.post("/scan", json=SCAN, headers=_bearer(alice))

    usage = client.get("/account/usage", headers=_bearer(alice)).json()

    assert usage == {
        "scans_paused": False,
        "quotas_apply": True,
        "scans_today": 1,
        "daily_scan_quota": 5,
        "active_scans": 1,
        "concurrent_scan_quota": 2,
        "ai_usage": {"days": 30, "scans": 0, "input_tokens": 0, "output_tokens": 0, "cached_tokens": 0},
    }
    assert client.get("/account/usage", headers=_bearer(admin)).json()["quotas_apply"] is False


def _ai_report(prompt: int, completion: int, cached: int) -> dict:
    record = {"node": "semantic_security_discovery", "prompt_tokens": prompt, "completion_tokens": completion, "cached_tokens": cached}
    return {"risk_assessment": {}, "metadata": {"llm_requested": True, "inference_usage": [record]}}


def test_usage_adds_up_the_users_ai_tokens(client):
    admin = _admin(client)
    alice = _user(client, admin)
    alice_id = db.get_user_by_email("alice@example.com")["id"]
    now = time.time()
    # a1 is older than 30 days, and "other" isn't Alice's.
    for scan_id, owner, created_at in (("a1", alice_id, now - 31 * 86400), ("a2", alice_id, now), ("other", "someone-else", now)):
        db.insert_scan(id=scan_id, target="t", status="running", created_at=created_at, provider="anthropic", owner_id=owner)
        db.update_scan(id=scan_id, status="done", finished_at=created_at, result=_ai_report(1000, 100, 400), error=None)

    usage = client.get("/account/usage", headers=_bearer(alice)).json()["ai_usage"]

    assert usage == {"days": 30, "scans": 1, "input_tokens": 1000, "output_tokens": 100, "cached_tokens": 400}


def test_a_rescan_counts_towards_the_quota(client, fake_runner):
    admin = _admin(client)
    alice = _user(client, admin)
    _limits(client, admin, daily_scan_quota=2, concurrent_scan_quota=None)
    scan_id = client.post("/scan", json=SCAN, headers=_bearer(alice)).json()["id"]
    db.update_scan(id=scan_id, status="done", finished_at=time.time(), result={"issues": []}, error=None)

    assert client.post(f"/scan/{scan_id}/rescan", headers=_bearer(alice)).status_code == 200
    refused = client.post(f"/scan/{scan_id}/rescan", headers=_bearer(alice))

    assert refused.status_code == 429
    assert len(fake_runner.submitted) == 2


# Per-user quotas


def _user_id(client, session: str) -> str:
    return client.get("/auth/session", headers=_bearer(session)).json()["user"]["id"]


def _set_quotas(client, admin: str, user_id: str, daily, concurrent):
    return client.put(
        f"/admin/users/{user_id}/quotas",
        json={"daily_scan_quota": daily, "concurrent_scan_quota": concurrent},
        headers=_bearer(admin),
    )


def test_a_users_own_quota_wins_over_every_other_level(temp_db, settings, monkeypatch):
    monkeypatch.setattr(settings, "daily_scan_quota", 3)
    quotas.save(quotas.ScanLimits(paused=False, daily=4, concurrent=1))

    assert quotas.current({"daily_scan_quota": 50, "concurrent_scan_quota": None}) == quotas.ScanLimits(paused=False, daily=50, concurrent=1)
    # 0 is no limit, for that user only.
    assert quotas.current({"daily_scan_quota": 0, "concurrent_scan_quota": 0}) == quotas.ScanLimits(paused=False, daily=None, concurrent=None)
    assert quotas.current() == quotas.ScanLimits(paused=False, daily=4, concurrent=1)


def test_an_override_applies_to_that_user_only_and_at_once(client):
    admin = _admin(client)
    alice = _user(client, admin)
    bob = _user(client, admin, "bob@example.com")
    _limits(client, admin, daily_scan_quota=1, concurrent_scan_quota=None)

    saved = _set_quotas(client, admin, _user_id(client, alice), 3, None)

    assert saved.status_code == 200
    assert saved.json() | {"scans_today": 0} == {
        "daily_scan_quota": 3,
        "concurrent_scan_quota": None,
        "server_daily_scan_quota": 1,
        "server_concurrent_scan_quota": None,
        "applies": True,
        "scans_today": 0,
        "active_scans": 0,
    }
    # Alice's next scans, in the same session.
    assert [client.post("/scan", json=SCAN, headers=_bearer(alice)).status_code for _ in range(4)] == [200, 200, 200, 429]
    assert [client.post("/scan", json=SCAN, headers=_bearer(bob)).status_code for _ in range(2)] == [200, 429]
    assert client.get("/account/usage", headers=_bearer(alice)).json()["daily_scan_quota"] == 3
    assert client.get("/account/usage", headers=_bearer(bob)).json()["daily_scan_quota"] == 1


def test_clearing_an_override_brings_the_user_back_to_the_server(client):
    admin = _admin(client)
    alice = _user(client, admin)
    alice_id = _user_id(client, alice)
    _limits(client, admin, daily_scan_quota=5, concurrent_scan_quota=2)
    _set_quotas(client, admin, alice_id, 0, 0)
    assert client.get("/account/usage", headers=_bearer(alice)).json()["daily_scan_quota"] is None

    _set_quotas(client, admin, alice_id, None, None)

    usage = client.get("/account/usage", headers=_bearer(alice)).json()
    assert (usage["daily_scan_quota"], usage["concurrent_scan_quota"]) == (5, 2)
    detail = client.get(f"/admin/users/{alice_id}", headers=_bearer(admin)).json()["quotas"]
    assert (detail["daily_scan_quota"], detail["concurrent_scan_quota"]) == (None, None)


def test_a_token_counts_against_its_owners_override(client):
    admin = _admin(client)
    alice = _user(client, admin)
    _limits(client, admin, daily_scan_quota=1, concurrent_scan_quota=None)
    _set_quotas(client, admin, _user_id(client, alice), 2, None)
    token = client.post("/account/tokens", json={"name": "CI", "password": PASSWORD}, headers=_bearer(alice)).json()["token"]

    assert [client.post("/scan", json=SCAN, headers=_bearer(token)).status_code for _ in range(3)] == [200, 200, 429]


def test_quota_changes_are_audited_with_what_changed(client):
    admin = _admin(client)
    alice = _user(client, admin)
    alice_id = _user_id(client, alice)

    _set_quotas(client, admin, alice_id, 50, None)
    _set_quotas(client, admin, alice_id, 50, None)  # No change: nothing to record.
    _set_quotas(client, admin, alice_id, None, 0)

    entries = [entry for entry in db.list_audit(20, 0, target_id=alice_id)[0] if entry["action"] == "user.quotas_changed"]
    assert [entry["detail"] for entry in entries] == [
        "per day: 50 → the server's; at once: the server's → no limit",
        "per day: the server's → 50",
    ]


@pytest.mark.parametrize("body", [{"daily_scan_quota": -1}, {"concurrent_scan_quota": "lots"}])
def test_an_override_must_be_a_count_or_null(client, body):
    admin = _admin(client)
    alice = _user(client, admin)

    assert client.put(f"/admin/users/{_user_id(client, alice)}/quotas", json=body, headers=_bearer(admin)).status_code == 422


def test_only_admins_set_overrides_and_admins_have_no_quota(client):
    admin = _admin(client)
    alice = _user(client, admin)
    alice_id = _user_id(client, alice)

    assert _set_quotas(client, alice, alice_id, 100, None).status_code == 403
    assert _set_quotas(client, admin, "nobody", 1, 1).status_code == 404
    admin_quotas = client.get(f"/admin/users/{_user_id(client, admin)}", headers=_bearer(admin)).json()["quotas"]
    assert admin_quotas["applies"] is False


# Simultaneous submissions


def test_simultaneous_inserts_take_exactly_the_free_slots(temp_db):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    limit, attempts = 3, 12
    start = threading.Barrier(attempts)

    def insert(index: int) -> int | None:
        start.wait()
        return db.insert_scan(
            id=f"scan{index}", target="https://example.com/s", status="pending", created_at=time.time(), provider=None,
            owner_id="alice", max_active=limit,
        )

    with ThreadPoolExecutor(attempts) as pool:
        inserted = list(pool.map(insert, range(attempts)))

    # Each one admitted gets its own number, in a row: none taken twice, none skipped.
    assert sorted(number for number in inserted if number is not None) == list(range(1, limit + 1))
    assert db.count_active_scans(owner_id="alice") == limit
    # Someone else's scans don't take alice's slots.
    assert db.insert_scan(id="bob1", target="https://example.com/s", status="pending", created_at=time.time(), provider=None, owner_id="bob", max_active=limit)


def test_simultaneous_submissions_queue_exactly_the_in_progress_quota(client, fake_runner):
    from concurrent.futures import ThreadPoolExecutor

    admin = _admin(client)
    alice = _user(client, admin)
    _limits(client, admin, daily_scan_quota=50, concurrent_scan_quota=3)

    with ThreadPoolExecutor(8) as pool:
        codes = list(pool.map(lambda _: client.post("/scan", json=SCAN, headers=_bearer(alice)).status_code, range(8)))

    assert sorted(codes) == [200] * 3 + [429] * 5
    assert len(fake_runner.submitted) == 3
    # The refused ones never counted towards today's quota.
    usage = client.get("/account/usage", headers=_bearer(alice)).json()
    assert (usage["active_scans"], usage["scans_today"]) == (3, 3)


def test_a_scan_refused_by_the_daily_quota_isnt_left_in_progress(client, fake_runner):
    admin = _admin(client)
    alice = _user(client, admin)
    _limits(client, admin, daily_scan_quota=1, concurrent_scan_quota=5)

    assert client.post("/scan", json=SCAN, headers=_bearer(alice)).status_code == 200
    assert client.post("/scan", json=SCAN, headers=_bearer(alice)).status_code == 429

    assert client.get("/account/usage", headers=_bearer(alice)).json()["active_scans"] == 1
