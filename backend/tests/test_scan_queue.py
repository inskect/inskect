from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db, scanner
from app.main import app


@pytest.fixture
def client(temp_db, fake_runner, monkeypatch):
    return TestClient(app)


def test_scan_is_queued_below_the_cap(client, fake_runner):
    response = client.post("/scan", json={"target": "https://example.com/skill.zip"})

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert len(fake_runner.submitted) == 1


def test_scan_is_rejected_when_the_queue_is_full(client, fake_runner):
    fake_runner.full = True

    response = client.post("/scan", json={"target": "https://example.com/skill.zip"})

    assert response.status_code == 503
    assert scanner.list_jobs(10, 0)[1] == 0


def test_scan_the_runner_cannot_take_is_rejected_before_it_is_stored(client, fake_runner):
    fake_runner.rejection = "AI review isn't available on this server yet"

    response = client.post("/scan", json={"target": "https://example.com/x", "llm": {"provider": "ollama"}})

    assert response.status_code == 422
    assert response.json()["detail"] == "AI review isn't available on this server yet"
    assert scanner.list_jobs(10, 0)[1] == 0


def test_a_scan_that_never_reaches_the_queue_is_marked_failed(client, fake_runner, monkeypatch):
    async def broken_submit(job):
        raise ConnectionError("queue unreachable")

    monkeypatch.setattr(fake_runner, "submit", broken_submit)

    response = client.post("/scan", json={"target": "https://example.com/skill.zip"})

    assert response.status_code == 503
    rows, total = scanner.list_jobs(10, 0)
    assert total == 1
    assert rows[0]["status"] == "error"
    assert db.count_active_scans() == 0
