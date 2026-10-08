from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app

VERDICTS = {"SAFE": ("LOW", 5), "CAUTION": ("MEDIUM", 40), "DO_NOT_INSTALL": ("CRITICAL", 90)}


@pytest.fixture
def client(temp_db):
    return TestClient(app)


@pytest.fixture
def history(temp_db):
    """30 scans: finished with each verdict and assorted scores, some failed, some still running."""
    rows = []
    for i in range(30):
        scan_id = f"s{i:02d}"
        target = f"https://github.com/acme/{chr(ord('a') + (i * 7) % 26)}{i:02d}"
        db.insert_scan(id=scan_id, target=target, status="pending", created_at=1000.0 + i, provider=None)
        if i % 10 == 3:
            db.update_scan(id=scan_id, status="error", finished_at=1000.0 + i, result=None, error="boom")
        elif i % 10 == 7:
            db.update_scan(id=scan_id, status="running", finished_at=None, result=None, error=None)
        else:
            recommendation = list(VERDICTS)[i % 3]
            severity, base = VERDICTS[recommendation]
            result = {"risk_assessment": {"score": base + i % 5, "severity": severity, "recommendation": recommendation}, "issues": []}
            db.update_scan(id=scan_id, status="done", finished_at=1001.0 + i, result=result, error=None)
        rows.append(scan_id)
    return rows


def _all_pages(client, **params) -> list[dict]:
    """Every scan, fetched 7 at a time, so a sort that only applied per page would show."""
    items, offset = [], 0
    while True:
        page = client.get("/scan", params={**params, "limit": 7, "offset": offset}).json()
        items += page["items"]
        offset += 7
        if offset >= page["total"]:
            return items


def test_the_default_stays_newest_first(client, history):
    assert [item["id"] for item in _all_pages(client)] == list(reversed(history))


@pytest.mark.parametrize("order", ["asc", "desc"])
def test_sorting_by_risk_score_covers_the_whole_history(client, history, order):
    items = _all_pages(client, sort="risk_score", order=order)

    assert len(items) == len({item["id"] for item in items}) == 30
    scored = [item["risk_score"] for item in items if item["risk_score"] is not None]
    assert scored == sorted(scored, reverse=order == "desc")
    # Failed and running scans have no score: last, whichever way.
    assert all(item["risk_score"] is None for item in items[len(scored) :])


def test_sorting_by_verdict_puts_the_riskiest_first(client, history):
    items = _all_pages(client, sort="verdict", order="desc")

    verdicts = [item["recommendation"] for item in items]
    rank = {"DO_NOT_INSTALL": 0, "CAUTION": 1, "SAFE": 2}
    known = [verdict for verdict in verdicts if verdict]
    assert known == sorted(known, key=rank.__getitem__)
    assert verdicts[len(known) :] == [None] * (30 - len(known))
    # Within a verdict, newest first.
    first_group = [item["created_at"] for item in items if item["recommendation"] == "DO_NOT_INSTALL"]
    assert first_group == sorted(first_group, reverse=True)


@pytest.mark.parametrize("order", ["asc", "desc"])
def test_sorting_by_target_and_status(client, history, order):
    targets = [item["target"] for item in _all_pages(client, sort="target", order=order)]
    assert targets == sorted(targets, reverse=order == "desc")

    statuses = [item["status"] for item in _all_pages(client, sort="status", order=order)]
    assert statuses == sorted(statuses, reverse=order == "desc")


def test_sorting_by_date_oldest_first(client, history):
    assert [item["id"] for item in _all_pages(client, sort="created_at", order="asc")] == history


@pytest.mark.parametrize("params", [{"sort": "error; DROP TABLE scans"}, {"sort": "id"}, {"order": "sideways"}])
def test_unknown_sorts_are_refused(client, history, params):
    assert client.get("/scan", params=params).status_code == 422


def test_a_users_history_is_sorted_within_their_own_scans(temp_db):
    db.insert_scan(id="mine", target="t", status="pending", created_at=1.0, provider=None, owner_id="alice")
    db.insert_scan(id="theirs", target="t", status="pending", created_at=2.0, provider=None, owner_id="bob")
    for scan_id, score in (("mine", 10), ("theirs", 99)):
        result = {"risk_assessment": {"score": score, "severity": "LOW", "recommendation": "SAFE"}, "issues": []}
        db.update_scan(id=scan_id, status="done", finished_at=3.0, result=result, error=None)

    rows, total = db.list_scans(10, 0, owner_id="alice", sort="risk_score", order="desc")

    assert [row["id"] for row in rows] == ["mine"] and total == 1


def test_the_sorts_have_indexes(temp_db):
    if temp_db != "sqlite":
        pytest.skip("checked on SQLite")
    store = db._store_or_raise()
    names = {row[0] for row in store._conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert {"scans_created_at", "scans_risk_score", "scans_status", "scans_owner_created_at", "scans_target_created_at"} <= names
