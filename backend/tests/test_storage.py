from __future__ import annotations

import sqlite3

import pytest

from app import db
from app.core.config import Settings
from app.storage import create_store, is_postgres_url
from app.storage.sqlite import MIGRATIONS, SQLiteStore


def test_result_round_trips_as_a_dict(temp_db):
    report = {"risk_assessment": {"score": 42, "severity": "HIGH", "recommendation": "CAUTION"}, "issues": []}
    db.insert_scan(id="a", target="t", status="pending", created_at=1.0, provider="anthropic")

    db.update_scan(id="a", status="done", finished_at=2.0, result=report, error=None)

    scan = db.get_scan("a")
    assert scan["result"] == report
    assert scan["provider"] == "anthropic"
    assert (scan["risk_score"], scan["severity"], scan["recommendation"]) == (42, "HIGH", "CAUTION")
    assert scan["ai_review"] is None


def test_ai_tokens_are_added_up_per_owner_and_period(temp_db):
    usage = [{"node": "meta_analyzer", "prompt_tokens": 1000, "completion_tokens": 100, "cached_tokens": 400}]
    report = {"risk_assessment": {}, "metadata": {"llm_requested": True, "inference_usage": usage}}
    for scan_id, owner, created_at in (("old", "alice", 1.0), ("new", "alice", 10.0), ("bob", "bob", 10.0), ("static", "alice", 10.0)):
        db.insert_scan(id=scan_id, target="t", status="running", created_at=created_at, provider=None, owner_id=owner)
        db.update_scan(id=scan_id, status="done", finished_at=created_at, result=None if scan_id == "static" else report, error=None)

    assert db.ai_token_totals(since=5.0, owner_id="alice") == {"scans": 1, "input_tokens": 1000, "output_tokens": 100, "cached_tokens": 400}
    assert db.ai_token_totals(since=0.0)["scans"] == 3
    assert db.ai_token_totals(since=5.0, owner_id="nobody") == {"scans": 0, "input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}


def test_history_records_whether_the_ai_review_ran(temp_db):
    report = {"risk_assessment": {}, "metadata": {"llm_requested": True, "llm_calls_succeeded": 0, "llm_error": "bad key"}}
    db.insert_scan(id="a", target="t", status="pending", created_at=1.0, provider="anthropic")

    db.update_scan(id="a", status="done", finished_at=2.0, result=report, error=None)

    rows, _ = db.list_scans(limit=10, offset=0)
    assert rows[0]["ai_review"] == "failed"


def test_list_scans_is_newest_first_with_a_total_and_no_report(temp_db):
    for index in range(3):
        db.insert_scan(id=f"s{index}", target="t", status="done", created_at=float(index), provider=None)

    rows, total = db.list_scans(limit=2, offset=0)

    assert total == 3
    assert [row["id"] for row in rows] == ["s2", "s1"]
    assert "result" not in rows[0]


def test_migrations_are_recorded_and_not_rerun(temp_db):
    db.init_db()  # A second startup against the same database.

    db.insert_scan(id="a", target="t", status="done", created_at=1.0, provider=None)
    assert db.get_scan("a") is not None


def test_a_database_from_before_migrations_is_adopted(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute(MIGRATIONS[0][1][0])  # The scans table, as older versions created it.
    conn.execute("INSERT INTO scans (id, target, status, created_at) VALUES ('kept', 't', 'done', 1.0)")
    conn.commit()
    conn.close()

    store = SQLiteStore(str(path), default_retention_days=None)

    assert store.get_scan("kept")["status"] == "done"
    assert store.get_retention_days() is None
    store.close()


@pytest.mark.parametrize(
    ("url", "expected"),
    [("postgres://u@h/db", True), ("postgresql://u@h/db", True), ("sqlite:///x.db", False), ("mysql://h/db", False)],
)
def test_is_postgres_url(url, expected):
    assert is_postgres_url(url) is expected


def test_create_store_rejects_non_postgres_urls(tmp_path):
    settings = Settings(_env_file=None, database_url="mysql://host/db", db_path=str(tmp_path / "x.db"))

    with pytest.raises(ValueError, match="postgres"):
        create_store(settings)


def test_create_store_defaults_to_sqlite(tmp_path):
    store = create_store(Settings(_env_file=None, db_path=str(tmp_path / "x.db")))

    assert isinstance(store, SQLiteStore)
    store.close()


def test_log_lines_go_away_with_their_scan(temp_db):
    for id in ("kept", "deleted", "expired"):
        db.insert_scan(id=id, target="t", status="done", created_at=2000.0 if id == "kept" else 1000.0, provider=None)
        db.append_log_line(id, f"{id} line", keep=500)

    db.delete_scan("deleted")
    db.delete_scans_older_than(1500.0)

    assert db.get_log_lines("kept") == ["kept line"]
    assert db.get_log_lines("deleted") == []
    assert db.get_log_lines("expired") == []


def test_progress_is_stored_on_the_scan(temp_db):
    db.insert_scan(id="a", target="t", status="running", created_at=1.0, provider=None)

    db.increment_progress("a")
    db.increment_progress("a")

    assert db.get_progress("a") == 2
    assert db.get_scan("a")["completed_steps"] == 2


def test_a_pending_signup_is_consumed_once_and_only_before_it_expires(temp_db):
    fields = {"email": "new@example.com", "password_hash": "hash", "created_at": 1.0, "expires_at": 100.0}
    db.create_pending_signup(token_hash="old", **fields)
    db.create_pending_signup(token_hash="new", **fields)
    db.create_pending_signup(token_hash="late", **{**fields, "email": "late@example.com"})

    # Signing up again cancels the address's earlier link.
    assert db.consume_pending_signup("old", now=50.0) is None
    assert db.consume_pending_signup("new", now=50.0) == {"email": "new@example.com", "password_hash": "hash"}
    assert db.consume_pending_signup("new", now=50.0) is None
    assert db.consume_pending_signup("late", now=150.0) is None


def test_the_retention_sweep_takes_only_expired_scans_lines_and_secrets(temp_db):
    for id, status, created_at in [("expired", "done", 1000.0), ("still-running", "running", 1000.0), ("recent", "done", 2000.0)]:
        db.insert_scan(id=id, target="t", status=status, created_at=created_at, provider=None)
        db.append_log_line(id, f"{id} line", keep=500)
        db.put_scan_secret(scan_id=id, encrypted_key=f"{id} secret", now=created_at)

    assert db.delete_scans_older_than(1500.0) == 1

    assert db.get_scan("expired") is None
    assert (db.get_log_lines("expired"), db.get_scan_secret("expired")) == ([], None)
    for id in ("still-running", "recent"):
        assert (db.get_log_lines(id), db.get_scan_secret(id)) == ([f"{id} line"], f"{id} secret")
