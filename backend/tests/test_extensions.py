"""The pieces a deployment may replace (app/core/extensions.py, docs/EXTENDING.md)."""

from __future__ import annotations

import json
import sys
import types
from contextlib import asynccontextmanager
from typing import ClassVar

import anyio
import pytest
from fastapi.testclient import TestClient

from app import db, monitoring, scanner, uploads
from app.core.config import get_settings
from app.core.extensions import ExtensionError, load
from app.jobs import create_runner
from app.main import app
from app.scanner import Job

REPORT = {"risk_assessment": {"score": 3, "severity": "LOW", "recommendation": "SAFE"}, "issues": []}


class Executor:
    """Scans nothing: records what it was asked, and returns REPORT."""

    calls: ClassVar[list[tuple[str, str | None, str | None]]] = []

    async def run(self, job, *, token):
        Executor.calls.append((job.target, job.upload, token))
        return REPORT


class Store:
    """Uploads held in memory."""

    kind = "memory"
    max_bytes = 1024
    files: ClassVar[dict[str, bytes]] = {}

    def save(self, scan_id, name, data):
        Store.files[scan_id] = data
        return f"mem:{scan_id}"

    async def read(self, ref):
        return Store.files[ref.removeprefix("mem:")]

    @asynccontextmanager
    async def local_copy(self, ref, name):
        yield f"/nowhere/{name}"

    async def delete(self, ref):
        Store.files.pop(ref.removeprefix("mem:"), None)

    def clear(self, keep):
        return None


class Broken:
    async def run(self, job, *, token):
        raise RuntimeError("the runner is gone")


class Runner:
    def on_startup(self):
        return None


@pytest.fixture(autouse=True)
def fake_module(monkeypatch):
    module = types.ModuleType("fake_extensions")
    module.Executor, module.Store, module.Broken, module.Runner = Executor, Store, Broken, Runner
    monkeypatch.setitem(sys.modules, "fake_extensions", module)
    Executor.calls, Store.files = [], {}
    scanner.get_executor.cache_clear()
    uploads.get_store.cache_clear()
    yield
    scanner.get_executor.cache_clear()
    uploads.get_store.cache_clear()


# Loading


def test_a_class_is_loaded_by_its_import_path():
    assert isinstance(load("fake_extensions:Executor", "SETTING"), Executor)
    assert isinstance(load("app.uploads:LocalUploadStore", "SETTING"), uploads.LocalUploadStore)


@pytest.mark.parametrize(
    ("path", "problem"),
    [
        ("fake_extensions", "must name a class as module:Class"),
        (":Executor", "must name a class as module:Class"),
        ("no_such_module:Executor", "can't be loaded"),
        ("fake_extensions:Nope", "can't be loaded"),
    ],
)
def test_a_path_that_cant_be_loaded_says_which_setting(path, problem):
    with pytest.raises(ExtensionError, match=problem) as error:
        load(path, "INSKECT_SCAN_EXECUTOR")
    assert "INSKECT_SCAN_EXECUTOR" in str(error.value)


def test_the_api_refuses_to_start_with_a_piece_it_cant_load(temp_db, monkeypatch):
    monkeypatch.setattr(get_settings(), "scan_executor", "no_such_module:Executor")

    with pytest.raises(ExtensionError, match="INSKECT_SCAN_EXECUTOR"), TestClient(app):
        pass


def test_the_defaults_are_the_built_in_pieces():
    settings = get_settings()

    assert type(create_runner(settings)).__name__ == "InProcessRunner"
    assert isinstance(scanner.get_executor(), scanner.LocalExecutor)
    assert isinstance(uploads.get_store(), uploads.LocalUploadStore)


# Replacing them


def test_the_job_runner_is_the_one_configured(monkeypatch):
    monkeypatch.setattr(get_settings(), "job_runner", "fake_extensions:Runner")

    assert isinstance(create_runner(get_settings()), Runner)


def test_scans_run_on_the_executor_configured(temp_db, monkeypatch):
    monkeypatch.setattr(get_settings(), "scan_executor", "fake_extensions:Executor")
    job = Job(id="s1", target="https://github.com/acme/skill", llm=None)
    db.insert_scan(id=job.id, target=job.target, status=job.status, created_at=job.created_at, provider=None)

    anyio.run(scanner.run_job, job)

    assert Executor.calls == [("https://github.com/acme/skill", None, None)]
    scan = db.get_scan("s1")
    assert (scan["status"], scan["result"]) == ("done", REPORT)


def test_a_failing_executor_fails_the_scan_with_its_message(temp_db, monkeypatch):
    monkeypatch.setattr(get_settings(), "scan_executor", "fake_extensions:Broken")
    job = Job(id="s2", target="https://github.com/acme/skill", llm=None)
    db.insert_scan(id=job.id, target=job.target, status=job.status, created_at=job.created_at, provider=None)

    anyio.run(scanner.run_job, job)

    scan = db.get_scan("s2")
    assert (scan["status"], scan["error"]) == ("error", "the runner is gone")


def test_uploads_go_to_the_store_configured(temp_db, fake_runner, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_store", "fake_extensions:Store")
    client = TestClient(app)

    response = client.post("/scan/upload", files={"file": ("SKILL.md", b"# A skill")}, data={"options": json.dumps({})})

    assert response.status_code == 200
    (job,) = fake_runner.submitted
    assert job.upload == f"mem:{job.id}" and Store.files[job.id] == b"# A skill"
    health = client.get("/health").json()
    assert (health["upload_store"], health["max_upload_bytes"]) == ("memory", 1024)


def test_the_stores_own_size_limit_applies(temp_db, fake_runner, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_store", "fake_extensions:Store")
    client = TestClient(app)

    response = client.post("/scan/upload", files={"file": ("SKILL.md", b"x" * 2048)}, data={"options": json.dumps({})})

    assert response.status_code == 422
    assert fake_runner.submitted == [] and Store.files == {}


# Alert rules


def test_an_extension_can_add_an_alert_rule(temp_db, monkeypatch):
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(monitoring, "send_alert", lambda title, text: sent.append((title, text)) or ["webhook"])
    monkeypatch.setattr(monitoring, "_rules", list(monitoring.rules()))
    rule = monitoring.Rule(
        "worker_down", "The scan workers are down", "Any worker error",
        "worker_error", 60, 3600, lambda now, message: monitoring.Measure(True, "1 error", f"A worker failed: {message}"),
    )

    monitoring.register_rule(rule)
    monitoring.record("worker_error", "connection refused")

    assert sent == [("The scan workers are down", "A worker failed: connection refused")]
    assert "worker_down" in [status["name"] for status in monitoring.rules_status()]
    with pytest.raises(ValueError, match="already named"):
        monitoring.register_rule(rule)
