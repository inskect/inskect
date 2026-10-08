from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import db, main, retention


def test_sweep_once_does_nothing_when_retention_disabled(temp_db):
    db.insert_scan(id="a", target="t", status="done", created_at=1.0, provider=None)

    assert retention.sweep_once() == 0
    assert db.get_scan("a") is not None


def test_sweep_once_deletes_scans_older_than_the_configured_window(temp_db):
    now = time.time()
    db.insert_scan(id="old", target="t", status="done", created_at=now - 10 * 86400, provider=None)
    db.insert_scan(id="new", target="t", status="done", created_at=now, provider=None)
    db.set_retention_days(5)

    deleted = retention.sweep_once()

    assert deleted == 1
    assert db.get_scan("old") is None
    assert db.get_scan("new") is not None


def test_set_retention_days_triggers_an_immediate_sweep(temp_db):
    now = time.time()
    db.insert_scan(id="old", target="t", status="done", created_at=now - 10 * 86400, provider=None)

    retention.set_retention_days(5)

    assert db.get_scan("old") is None


def test_start_and_stop_manage_the_background_task(temp_db):
    async def scenario():
        retention.start()
        task = retention._task
        assert task is not None
        await asyncio.sleep(0)
        assert not task.done()

        retention.stop()
        assert retention._task is None
        await asyncio.sleep(0)
        assert task.cancelled() or task.done()

    asyncio.run(scenario())


@pytest.mark.parametrize("starts", [True, False])
def test_the_background_sweep_follows_its_setting(temp_db, monkeypatch, starts):
    started = []
    monkeypatch.setattr(retention, "start", lambda: started.append(True))
    monkeypatch.setattr(main, "get_runner", lambda: SimpleNamespace(on_startup=lambda: None))
    monkeypatch.setattr(main.settings, "retention_loop", starts)

    with TestClient(main.app):
        pass

    assert started == ([True] if starts else [])
