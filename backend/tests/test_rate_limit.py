from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import rate_limit
from app.auth import passwords
from app.core.config import Settings, get_settings
from app.main import app

PASSWORD = "correct horse battery"


@pytest.fixture(params=["memory", "database"])
def store(request, temp_db, monkeypatch):
    """Each store, on each database engine, with a clock the test moves."""
    now = {"t": 1000.0}
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: now["t"])
    monkeypatch.setattr(rate_limit.time, "time", lambda: now["t"])
    store = rate_limit.MemoryRateLimitStore() if request.param == "memory" else rate_limit.DatabaseRateLimitStore()
    store.now = now
    return store


def test_allows_up_to_the_limit(store):
    assert [store.hit("client-a", limit=5, window_seconds=60) for _ in range(5)] == [None] * 5


def test_refuses_once_over_the_limit_and_says_when_to_retry(store):
    for _ in range(4):
        store.hit("client-a", limit=5, window_seconds=60)
    store.now["t"] += 20
    store.hit("client-a", limit=5, window_seconds=60)

    assert store.hit("client-a", limit=5, window_seconds=60) == pytest.approx(40)


def test_different_keys_are_isolated(store):
    for _ in range(5):
        store.hit("client-a", limit=5, window_seconds=60)

    assert store.hit("client-b", limit=5, window_seconds=60) is None


def test_hits_expire_after_the_window(store):
    for _ in range(5):
        store.hit("client-a", limit=5, window_seconds=60)
    assert store.hit("client-a", limit=5, window_seconds=60) is not None

    store.now["t"] += 61

    assert store.hit("client-a", limit=5, window_seconds=60) is None


def test_refused_hits_are_not_counted(store):
    for _ in range(5):
        store.hit("client-a", limit=5, window_seconds=60)
    for _ in range(10):
        store.hit("client-a", limit=5, window_seconds=60)

    store.now["t"] += 61

    assert [store.hit("client-a", limit=5, window_seconds=60) for _ in range(5)] == [None] * 5


def test_a_forgotten_hit_frees_its_slot(store):
    for _ in range(5):
        store.hit("client-a", limit=5, window_seconds=60)

    store.forget("client-a")

    assert store.hit("client-a", limit=5, window_seconds=60) is None
    assert store.hit("client-a", limit=5, window_seconds=60) is not None


def test_memory_store_evicts_the_oldest_client_past_the_tracked_cap():
    store = rate_limit.MemoryRateLimitStore()
    for i in range(rate_limit._MAX_TRACKED_CLIENTS):
        store.hit(f"client-{i}", limit=5, window_seconds=60)
    store.hit("client-overflow", limit=5, window_seconds=60)

    assert "client-0" not in store._hits
    assert "client-overflow" in store._hits


def test_the_database_store_is_shared_between_instances(temp_db):
    # Two stores stand in for two app instances: each sees the other's hits.
    first, second = rate_limit.DatabaseRateLimitStore(), rate_limit.DatabaseRateLimitStore()
    for _ in range(3):
        first.hit("user:alice", limit=5, window_seconds=60)
    for _ in range(2):
        second.hit("user:alice", limit=5, window_seconds=60)

    assert first.hit("user:alice", limit=5, window_seconds=60) is not None


@pytest.mark.parametrize(
    ("database_url", "override", "expected"),
    [
        (None, None, "memory"),
        ("postgresql://db/x", None, "database"),
        (None, "database", "database"),
        ("postgresql://db/x", "memory", "memory"),
    ],
)
def test_the_store_follows_the_database_unless_overridden(database_url, override, expected):
    assert rate_limit.rate_limit_store_kind(Settings(_env_file=None, database_url=database_url, rate_limit_store=override)) == expected


# Scans


@pytest.fixture(autouse=True)
def _fast_hashing(monkeypatch):
    monkeypatch.setattr(passwords, "_N", 2**10)
    passwords.dummy_hash.cache_clear()
    yield
    passwords.dummy_hash.cache_clear()


@pytest.fixture(params=["memory", "database"])
def accounts(request, temp_db, fake_runner, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "auth", "accounts")
    monkeypatch.setattr(settings, "allow_signup", None)
    monkeypatch.setattr(settings, "rate_limit_store", request.param)
    monkeypatch.setattr(settings, "scan_rate_limit", 2)
    monkeypatch.setattr(settings, "scan_ip_rate_limit", 3)
    return TestClient(app)


def _sign_up(client, email: str, address: str = "203.0.113.7") -> dict[str, str]:
    response = client.post("/auth/signup", json={"email": email, "password": PASSWORD}, headers={"X-Forwarded-For": address})
    return {"Authorization": f"Bearer {response.json()['token']}", "X-Forwarded-For": address}


def _scan(client, headers):
    return client.post("/scan", json={"target": "https://example.com/skill.zip"}, headers=headers)


def test_scans_are_limited_per_user_not_per_address(accounts):
    alice = _sign_up(accounts, "alice@example.com")
    bob = _sign_up(accounts, "bob@example.com")

    assert [_scan(accounts, alice).status_code for _ in range(3)] == [200, 200, 429]
    assert _scan(accounts, bob).status_code == 200


def test_a_user_keeps_their_limit_from_another_address(accounts):
    alice = _sign_up(accounts, "alice@example.com")
    for _ in range(2):
        _scan(accounts, alice)

    assert _scan(accounts, {**alice, "X-Forwarded-For": "198.51.100.1"}).status_code == 429


def test_more_accounts_from_one_address_do_not_buy_more_scans(accounts):
    users = [_sign_up(accounts, f"user{i}@example.com") for i in range(4)]

    responses = [_scan(accounts, headers) for headers in users]

    assert [r.status_code for r in responses] == [200, 200, 200, 429]
    assert "address" in responses[-1].json()["detail"]
    other_address = _sign_up(accounts, "carol@example.com", address="198.51.100.1")
    assert _scan(accounts, other_address).status_code == 200


def test_a_refused_scan_says_when_to_retry(accounts):
    alice = _sign_up(accounts, "alice@example.com")
    for _ in range(2):
        _scan(accounts, alice)

    response = _scan(accounts, alice)

    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= 60
    assert "try again in" in response.json()["detail"]


def test_without_accounts_scans_are_limited_per_address(temp_db, fake_runner, monkeypatch):
    monkeypatch.setattr(get_settings(), "auth", "none")
    client = TestClient(app)

    statuses = [_scan(client, {"X-Forwarded-For": "203.0.113.7"}).status_code for _ in range(6)]

    assert statuses == [200] * 5 + [429]
    assert _scan(client, {"X-Forwarded-For": "198.51.100.1"}).status_code == 200
