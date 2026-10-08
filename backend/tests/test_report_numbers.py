"""Each owner numbers their own inspection reports (app/storage/base.py's NEXT_REPORT_NO)."""

from __future__ import annotations

import sqlite3
import time

from fastapi.testclient import TestClient

from app import db, scanner
from app.main import app
from app.storage.sqlite import MIGRATIONS, SQLiteStore


def _insert(id: str, owner: str | None, created_at: float = 1.0, **options) -> int | None:
    return db.insert_scan(id=id, target="https://example.com/x", status="pending", created_at=created_at, provider=None, owner_id=owner, **options)


def test_each_owner_numbers_their_reports_from_one(temp_db):
    numbers = [_insert(id, owner) for id, owner in (("a1", "alice"), ("b1", "bob"), ("a2", "alice"), ("n1", None), ("a3", "alice"), ("n2", None))]

    assert numbers == [1, 1, 2, 1, 3, 2]
    assert db.get_scan("a3")["report_no"] == 3
    rows, _ = db.list_scans(limit=10, offset=0, owner_id="bob")
    assert [row["report_no"] for row in rows] == [1]


def test_a_scan_refused_for_the_owners_quota_takes_no_number(temp_db):
    assert _insert("a1", "alice", max_active=1) == 1

    assert _insert("a2", "alice", max_active=1) is None  # a1 is still pending
    db.update_scan(id="a1", status="done", finished_at=2.0, result=None, error=None)

    assert _insert("a3", "alice", max_active=1) == 2


def test_numbers_keep_counting_after_a_scan_is_deleted(temp_db):
    _insert("a1", "alice")
    _insert("a2", "alice")
    db.delete_scan("a2")

    assert _insert("a3", "alice") == 3


def test_deleting_an_account_forgets_its_count(temp_db):
    db.create_user(id="alice", email="alice@example.com", password_hash="x", role="user", created_at=1.0)
    _insert("a1", "alice")

    db.delete_user("alice")
    db.create_user(id="alice", email="alice@example.com", password_hash="x", role="user", created_at=2.0)

    assert _insert("a2", "alice") == 1


def test_the_api_reports_the_number(temp_db, fake_runner):
    client = TestClient(app)

    queued = client.post("/scan", json={"target": "https://github.com/acme/skill"}).json()

    assert fake_runner.submitted[0].report_no == 1
    assert client.get(f"/scan/{queued['id']}").json()["report_no"] == 1
    assert client.get("/scan").json()["items"][0]["report_no"] == 1


def test_a_job_read_back_carries_its_number(temp_db):
    job = scanner.create_job("https://example.com/x", None, owner_id="alice")

    assert scanner.job_from_row(db.get_scan(job.id)).report_no == job.report_no == 1


def test_the_migration_numbers_existing_scans_per_owner_by_date(tmp_path):
    path = tmp_path / "before.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at REAL NOT NULL)")
    for version, statements in MIGRATIONS:
        if version == 28:
            break
        for statement in statements:
            conn.execute(statement)
        conn.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)", (version, time.time()))
    for id, owner, created_at in (("late", "alice", 30.0), ("early", "alice", 10.0), ("bob", "bob", 20.0), ("anon", None, 5.0)):
        conn.execute("INSERT INTO scans (id, target, status, created_at, owner_id) VALUES (?, 't', 'done', ?, ?)", (id, created_at, owner))
    conn.commit()
    conn.close()

    store = SQLiteStore(str(path), default_retention_days=None)

    assert {id: store.get_scan(id)["report_no"] for id in ("early", "late", "bob", "anon")} == {"early": 1, "late": 2, "bob": 1, "anon": 1}
    assert store.insert_scan(id="next", target="t", status="pending", created_at=40.0, provider=None, owner_id="alice") == 3
    store.close()
