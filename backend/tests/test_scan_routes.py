from __future__ import annotations

import asyncio
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from app import db, scan_logs
from app.core.config import get_settings
from app.main import app


@pytest.fixture
def client(temp_db, fake_runner, monkeypatch):
    client = TestClient(app)
    client.scheduled = fake_runner.submitted
    return client


def _insert(id: str, created_at: float, status: str = "done") -> None:
    db.insert_scan(id=id, target=f"https://example.com/{id}", status=status, created_at=created_at, provider=None)


def test_start_scan_queues_a_pending_job(client):
    response = client.post("/scan", json={"target": "  https://example.com/skill.zip  "})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert [job.id for job in client.scheduled] == [body["id"]]
    assert client.scheduled[0].target == "https://example.com/skill.zip"


def test_a_github_file_link_is_scanned_as_the_raw_file(client):
    response = client.post("/scan", json={"target": "https://github.com/anthropics/skills/blob/main/skills/pdf/SKILL.md"})

    raw = "https://raw.githubusercontent.com/anthropics/skills/main/skills/pdf/SKILL.md"
    assert client.scheduled[0].target == raw
    # The history shows what was scanned.
    assert client.get(f"/scan/{response.json()['id']}").json()["target"] == raw


@pytest.mark.parametrize("target", ["", "   ", "file:///etc/passwd", "/local/path", "ftp://example.com/x"])
def test_start_scan_rejects_non_http_targets(client, target):
    response = client.post("/scan", json={"target": target})

    assert response.status_code == 422
    assert client.scheduled == []


def test_start_scan_requires_an_api_key_for_remote_providers(client):
    response = client.post("/scan", json={"target": "https://example.com/x", "llm": {"provider": "openai"}})

    assert response.status_code == 422


def test_start_scan_is_rate_limited_per_client(client):
    statuses = [client.post("/scan", json={"target": "https://example.com/x"}).status_code for _ in range(6)]

    assert statuses == [200] * 5 + [429]


def test_history_is_newest_first_and_paginated(client):
    for i in range(3):
        _insert(f"scan-{i}", created_at=float(i))

    response = client.get("/scan", params={"limit": 2, "offset": 0})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert [item["id"] for item in body["items"]] == ["scan-2", "scan-1"]


def test_read_scan_returns_the_stored_job(client):
    _insert("abc", created_at=1.0, status="running")

    response = client.get("/scan/abc")

    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_a_failed_ai_review_is_reported_on_the_scan_and_in_history(client):
    _insert("ai", created_at=1.0)
    report = {"risk_assessment": {}, "metadata": {"llm_requested": True, "llm_calls_succeeded": 0, "llm_error": "bad key"}}
    db.update_scan(id="ai", status="done", finished_at=2.0, result=report, error=None)

    assert client.get("/scan/ai").json()["ai_review"] == "failed"
    assert client.get("/scan/ai").json()["ai_tokens"] is None
    assert client.get("/scan").json()["items"][0]["ai_review"] == "failed"


def test_a_scan_reports_its_ai_tokens(client):
    _insert("ai", created_at=1.0)
    usage = [{"node": "meta_analyzer", "prompt_tokens": 500, "completion_tokens": 50, "cached_tokens": 100}]
    report = {"risk_assessment": {}, "metadata": {"llm_requested": True, "inference_usage": usage}}
    db.update_scan(id="ai", status="done", finished_at=2.0, result=report, error=None)

    assert client.get("/scan/ai").json()["ai_tokens"] == {"input": 500, "output": 50, "cached": 100}


BASELINE = """version: 2
rules:
  - id: "TR3"
    reason: "Accepted: the skill documents this"
"""


def test_a_scan_keeps_how_deep_it_follows_references(client):
    scan_id = client.post("/scan", json={"target": "https://example.com/skill.zip", "transitive_depth": 2}).json()["id"]

    assert db.get_scan(scan_id)["transitive_depth"] == 2


def test_references_cant_be_followed_deeper_than_the_server_allows(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "transitive_max_depth", 1)
    response = client.post("/scan", json={"target": "https://example.com/skill.zip", "transitive_depth": 2})
    assert response.status_code == 422
    assert "at most 1 level deep" in response.json()["detail"]

    monkeypatch.setattr(settings, "transitive_max_depth", 0)
    response = client.post("/scan", json={"target": "https://example.com/skill.zip", "transitive_depth": 1})
    assert "turned off" in response.json()["detail"]


def test_a_scan_keeps_its_baseline(client):
    scan_id = client.post("/scan", json={"target": "https://example.com/skill.zip", "baseline": BASELINE}).json()["id"]

    assert db.get_scan(scan_id)["baseline"] == BASELINE


@pytest.mark.parametrize(
    ("baseline", "message"),
    [
        ("version: 2\nfingerprints:\n  - hash: nope\n", "Couldn't use the baseline file"),
        ("[unclosed", "Couldn't use the baseline file"),
        ("x" * (256 * 1024 + 1), "larger than 256 KB"),
    ],
    ids=["invalid-fingerprint", "not-yaml", "too-large"],
)
def test_a_bad_baseline_is_refused_before_the_scan_is_queued(client, baseline, message):
    response = client.post("/scan", json={"target": "https://example.com/skill.zip", "baseline": baseline})

    assert response.status_code == 422
    assert message in str(response.json()["detail"])
    assert "/tmp/" not in str(response.json()["detail"])
    assert db.list_scans(10, 0)[1] == 0


def test_a_scan_keeps_its_opt_in_to_the_skills_own_baseline(client):
    scan_id = client.post("/scan", json={"target": "https://github.com/acme/skill", "use_shipped_baseline": True}).json()["id"]

    assert db.get_scan(scan_id)["use_shipped_baseline"]
    plain = client.post("/scan", json={"target": "https://github.com/acme/skill"}).json()["id"]
    assert not db.get_scan(plain)["use_shipped_baseline"]


def test_a_baseline_file_and_the_skills_own_cant_both_be_used(client):
    response = client.post("/scan", json={"target": "https://github.com/acme/skill", "baseline": BASELINE, "use_shipped_baseline": True})

    assert response.status_code == 422 and "not both" in response.json()["detail"]
    mcp = client.post("/scan", json={"target": "io.github.acme/weather", "use_shipped_baseline": True})
    assert mcp.status_code == 422


def test_a_scans_baseline_downloads_with_the_reason_given(client):
    _insert("b", created_at=1.0)
    generated = {
        "version": 2,
        "scanner_version": "2.12.0",
        "rules": [],
        "fingerprints": [{"hash": "sha256:" + "a" * 64, "rule_id": "TR3", "file": "SKILL.md", "reason": "Accepted finding (auto-generated baseline)"}],
    }
    db.update_scan(id="b", status="done", finished_at=2.0, result={"issues": [], "generated_baseline": generated}, error=None)

    body = client.get("/scan/b/baseline", params={"reason": "Reviewed by the security team"}).json()

    assert body["filename"] == ".skillspector-baseline.yaml"
    assert "sha256:" + "a" * 64 in body["content"]
    assert "Reviewed by the security team" in body["content"]
    assert "auto-generated" not in body["content"]


def test_a_scan_without_findings_has_no_baseline(client):
    _insert("c", created_at=1.0)
    db.update_scan(id="c", status="done", finished_at=2.0, result={"issues": []}, error=None)

    assert client.get("/scan/c/baseline").status_code == 404


def test_unknown_scan_is_404_for_read_and_delete(client):
    assert client.get("/scan/missing").status_code == 404
    assert client.delete("/scan/missing").status_code == 404


def test_delete_scan_removes_it(client):
    _insert("abc", created_at=1.0)

    assert client.delete("/scan/abc").status_code == 204
    assert db.get_scan("abc") is None


def test_logs_for_unknown_scan_are_not_found(client):
    assert client.get("/scan/missing/logs").status_code == 404


@pytest.mark.parametrize("store", [scan_logs.MemoryLogStore, scan_logs.DatabaseLogStore])
def test_history_reads_progress_without_a_query_per_scan(client, monkeypatch, store, request):
    log_store = store()
    monkeypatch.setattr(scan_logs, "_store", log_store)
    request.addfinalizer(log_store.close)
    for i, status in enumerate(["running", "pending", "error", "done"]):
        _insert(f"scan-{i}", created_at=float(i), status=status)
    scan_logs.increment_progress("scan-0")
    scan_logs.increment_progress("scan-0")

    def no_query(scan_id: str) -> int:
        raise AssertionError(f"progress of {scan_id} read with its own query")

    monkeypatch.setattr(db, "get_progress", no_query)
    items = {item["id"]: item["completed_steps"] for item in client.get("/scan").json()["items"]}

    assert items["scan-0"] == 2
    assert items["scan-1"] == items["scan-2"] == 0


@pytest.mark.parametrize("path", ["/scan/{}", "/scan/{}/logs"])
def test_a_slow_database_call_doesnt_hold_up_other_requests(client, monkeypatch, path):
    _insert("slow", created_at=1.0, status="running")
    _insert("fast", created_at=2.0, status="running")
    entered, release = threading.Event(), threading.Event()
    released = []
    get_scan = db.get_scan

    def slow_get_scan(scan_id: str):
        if scan_id == "slow":
            entered.set()
            # Run on the event loop, this would hold up every request until it gave up.
            released.append(release.wait(timeout=3))
        return get_scan(scan_id)

    monkeypatch.setattr(db, "get_scan", slow_get_scan)

    async def both():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            slow = asyncio.create_task(http.get(path.format("slow")))
            await asyncio.to_thread(entered.wait, 3)
            try:
                fast = await http.get(path.format("fast"))
            finally:
                release.set()
            return fast, await slow

    fast, slow = asyncio.run(both())

    assert fast.status_code == slow.status_code == 200
    # The other request answered while the slow one was still waiting on the database.
    assert released and all(released)


def test_scan_logs_send_only_the_lines_after_the_cursor(client, monkeypatch):
    monkeypatch.setattr(scan_logs, "_store", scan_logs.MemoryLogStore())
    _insert("abc", created_at=1.0, status="running")
    scan_logs.append("abc", "one")
    first = client.get("/scan/abc/logs").json()
    scan_logs.append("abc", "two")

    second = client.get("/scan/abc/logs", params={"after": first["cursor"]}).json()

    assert first["lines"] == ["one"]
    assert second["lines"] == ["two"]
    assert client.get("/scan/abc/logs", params={"after": second["cursor"]}).json() == {"lines": [], "cursor": second["cursor"]}
