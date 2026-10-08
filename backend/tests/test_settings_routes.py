from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


@pytest.fixture
def client(temp_db, monkeypatch):
    monkeypatch.setattr(get_settings(), "auth", "none")
    return TestClient(app)


def test_settings_are_readable(client):
    response = client.get("/settings")

    assert response.status_code == 200
    assert response.json() == {"scan_retention_days": None, "allow_signup": False, "scans_paused": False, "daily_scan_quota": None, "concurrent_scan_quota": None}


def test_without_accounts_anyone_can_update_retention(client):
    response = client.put("/settings", json={"scan_retention_days": 7})

    assert response.status_code == 200
    assert client.get("/settings").json()["scan_retention_days"] == 7


@pytest.mark.parametrize("days", [0, -1])
def test_retention_must_be_positive(client, days):
    response = client.put("/settings", json={"scan_retention_days": days})

    assert response.status_code == 422
