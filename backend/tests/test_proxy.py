from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import proxy
from app.api.routes import shared
from app.core.config import get_settings
from app.main import app


@pytest.fixture
def client(temp_db):
    return TestClient(app)


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setattr(get_settings(), "proxy_secret", "s3cret")
    return "s3cret"


def test_with_a_proxy_secret_only_the_web_app_gets_an_answer(client, secret):
    assert client.get("/health").status_code == 403
    assert client.get("/health", headers={proxy.SECRET_HEADER: "wrong"}).status_code == 403
    assert client.get("/scan/anything", headers={proxy.SECRET_HEADER: "wrong"}).status_code == 403
    assert client.get("/health", headers={proxy.SECRET_HEADER: secret}).status_code == 200


def test_without_one_the_private_api_answers_as_before(client):
    assert client.get("/health").status_code == 200


def test_each_visitor_the_web_app_passes_on_has_a_rate_limit_of_their_own(client, secret, monkeypatch):
    monkeypatch.setattr(shared, "SHARED_RATE_LIMIT", 2)

    def get(address: str, **headers):
        headers = {proxy.SECRET_HEADER: secret, proxy.CLIENT_IP_HEADER: address, **headers}
        return client.get("/shared/nope", headers=headers).status_code

    assert [get("203.0.113.1") for _ in range(3)] == [404, 404, 429]
    # Another visitor through the same web app, whatever X-Forwarded-For a proxy on the way set.
    assert get("203.0.113.2", **{"X-Forwarded-For": "203.0.113.1"}) == 404


def test_a_proxy_the_web_app_doesnt_trust_shows_in_the_backoffice(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "auth", "none")
    assert client.get("/admin/overview").json()["health"]["proxy_warning"] is None

    client.get("/health", headers={proxy.UNTRUSTED_HEADER: "1"})

    assert "NUXT_TRUST_PROXY" in client.get("/admin/overview").json()["health"]["proxy_warning"]
