from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_the_model_catalog_suggests_skillspectors_models_per_provider():
    catalog = TestClient(app).get("/models").json()

    assert set(catalog) >= {"anthropic", "openai", "azure_openai", "openai_compatible", "nv_build", "ollama"}
    for entry in catalog.values():
        # The default is always offered, first when skillspector's registry doesn't list it.
        assert entry["default"] is None or entry["default"] in entry["models"]
    assert "claude-sonnet-4-6" in catalog["anthropic"]["models"]
