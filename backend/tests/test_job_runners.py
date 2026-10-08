from __future__ import annotations

import asyncio
from pathlib import Path

import anyio
import pytest

from app import db, scanner, uploads
from app.core.config import get_settings
from app.jobs.in_process import InProcessRunner
from app.scanner import Job, LLMConfig

REPORT = {"risk_assessment": {"score": 7, "severity": "LOW", "recommendation": "SAFE"}, "issues": []}


@pytest.fixture
def fake_graph(monkeypatch):
    """Stands in for skillspector's graph: records each scanned target and returns REPORT."""
    calls: list[str] = []

    def invoke(job_id: str, target: str, use_llm: bool, baseline: str | None = None, transitive_depth: int | None = None, *, label=None, use_shipped_baseline=False) -> dict:
        calls.append(target)
        return REPORT

    monkeypatch.setattr(scanner, "_invoke_graph", invoke)
    return calls


def _pending_job(id: str = "scan1") -> Job:
    job = Job(id=id, target=f"https://example.com/{id}", llm=None)
    db.insert_scan(id=job.id, target=job.target, status=job.status, created_at=job.created_at, provider=None)
    return job


# In-process runner


def test_in_process_runner_runs_a_scan_to_completion(temp_db, fake_graph):
    job = _pending_job()

    async def main():
        runner = InProcessRunner()
        await runner.submit(job)
        await asyncio.gather(*runner._tasks)

    asyncio.run(main())

    scan = db.get_scan(job.id)
    assert scan["status"] == "done"
    assert scan["result"] == REPORT
    assert fake_graph == [job.target]


def test_in_process_runner_is_full_at_max_queued_scans(monkeypatch):
    runner = InProcessRunner()
    monkeypatch.setattr(runner, "_tasks", {object(), object()})
    monkeypatch.setattr(scanner.db, "count_active_scans", lambda: 0)  # Not consulted in-process.

    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_queued_scans", 2)
    assert runner.is_full()
    monkeypatch.setattr(get_settings(), "max_queued_scans", 3)
    assert not runner.is_full()


async def _restart() -> InProcessRunner:
    """A new process starting, and running what it picked up to an end."""
    runner = InProcessRunner()
    runner.on_startup()
    await asyncio.gather(*runner._tasks)
    return runner


def _ai_job(id: str, llm: LLMConfig | None) -> Job:
    job = Job(id=id, target=f"https://example.com/{id}", llm=llm)
    db.insert_scan(id=job.id, target=job.target, status=job.status, created_at=job.created_at, provider=llm.provider if llm else None)
    return job


def test_a_restart_runs_the_scans_a_previous_process_left_unfinished(temp_db, fake_graph):
    _pending_job("waiting")
    _pending_job("midway")
    db.update_scan(id="midway", status="running", finished_at=None, result=None, error=None)
    db.start_attempt("midway")

    anyio.run(_restart)

    assert {db.get_scan(id)["status"] for id in ("waiting", "midway")} == {"done"}
    assert sorted(fake_graph) == ["https://example.com/midway", "https://example.com/waiting"]
    assert db.get_scan("midway")["attempts"] == 2


def test_a_scan_that_never_finishes_stops_after_a_few_attempts(temp_db, fake_graph):
    from app.jobs import in_process

    _pending_job("stuck")
    db.update_scan(id="stuck", status="running", finished_at=None, result=None, error=None)
    for _ in range(in_process.MAX_ATTEMPTS):
        db.start_attempt("stuck")

    anyio.run(_restart)

    scan = db.get_scan("stuck")
    assert scan["status"] == "error"
    assert scan["error"] == f"The scan didn't finish after {in_process.MAX_ATTEMPTS} attempts: the API stopped during each one"
    assert fake_graph == []


def test_a_scan_cancelled_by_a_shutdown_waits_to_run_again(temp_db, monkeypatch):
    import threading

    release = threading.Event()

    def slow(*args, **kwargs):
        release.wait(5)
        return REPORT

    monkeypatch.setattr(scanner, "_invoke_graph", slow)
    upload = uploads.save_local("cut", "skill.zip", b"zip")
    job = _pending_job("cut")
    job.upload = upload

    async def shutdown_midway():
        runner = InProcessRunner()
        await runner.submit(job)
        await asyncio.sleep(0.2)
        for task in runner._tasks:
            task.cancel()
        await asyncio.gather(*runner._tasks, return_exceptions=True)
        # The scan's thread can't be cancelled: let it end, rather than have anyio.run wait it out.
        release.set()

    anyio.run(shutdown_midway)

    scan = db.get_scan("cut")
    assert (scan["status"], scan["finished_at"], scan["error"]) == ("pending", None, None)
    assert Path(upload).exists()


def test_an_ai_scans_one_off_key_is_kept_to_run_it_again(temp_db, fake_graph, monkeypatch):
    from app import secrets_box
    from app.jobs import in_process

    monkeypatch.setattr(get_settings(), "secret_key", secrets_box.generate_key())
    llm = LLMConfig(provider="openai_compatible", api_key="sk-one-off-key-1234567890", base_url="https://llm.example.com/v1")
    job = _ai_job("ai", llm)

    async def held_then_restarted():
        runner = InProcessRunner()
        monkeypatch.setattr(runner, "_start", lambda job: None)  # The process stops before it runs.
        await runner.submit(job)

    anyio.run(held_then_restarted)

    resumed = in_process._job_for(db.get_scan("ai"))
    assert (resumed.llm.api_key, resumed.llm.base_url) == (llm.api_key, llm.base_url)


def test_without_a_secret_key_only_one_off_key_scans_fail_on_restart(temp_db, fake_graph, monkeypatch):
    monkeypatch.setattr(get_settings(), "secret_key", None)
    _ai_job("keyed", LLMConfig(provider="openai", api_key="sk-one-off-key-1234567890"))
    _ai_job("local", LLMConfig(provider="ollama"))
    _pending_job("static")

    anyio.run(_restart)

    keyed = db.get_scan("keyed")
    assert keyed["status"] == "error" and "INSKECT_SECRET_KEY" in keyed["error"]
    assert (db.get_scan("local")["status"], db.get_scan("static")["status"]) == ("done", "done")


def test_a_restart_keeps_only_the_uploads_of_scans_it_runs_again(temp_db, fake_graph):
    kept = Path(uploads.save_local("again", "skill.zip", b"zip"))
    orphan = Path(uploads.save_local("gone", "skill.zip", b"zip"))
    job = Job(id="again", target="upload:skill.zip", llm=None, upload=str(kept))
    db.insert_scan(id=job.id, target=job.target, status=job.status, created_at=job.created_at, provider=None, upload=job.upload)

    async def at_startup():
        runner = InProcessRunner()
        runner.on_startup()
        # Before the resumed scan runs: its upload is still there, the orphan is gone.
        assert kept.exists() and not orphan.exists()
        await asyncio.gather(*runner._tasks)

    anyio.run(at_startup)

    assert db.get_scan("again")["status"] == "done"
    # Deleted once scanned, as always.
    assert not kept.exists()


# Any runner


def test_a_failing_scan_is_recorded_as_an_error_not_retried(temp_db, monkeypatch):
    def explode(job_id, target, use_llm, baseline=None, transitive_depth=None, *, label=None, use_shipped_baseline=False):
        raise RuntimeError("clone failed")

    monkeypatch.setattr(scanner, "_invoke_graph", explode)
    job = _pending_job()

    anyio.run(scanner.run_job, job)  # Returns normally: the failure is the scan's, not the runner's.

    scan = db.get_scan(job.id)
    assert scan["status"] == "error"
    assert scan["error"] == "clone failed"
