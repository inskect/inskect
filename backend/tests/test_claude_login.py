from __future__ import annotations

import os
import subprocess

import anyio
import pytest

from app import claude_login


def _fake_run(stdout: bytes, returncode: int = 0, calls: list | None = None):
    def run(args, **kwargs):
        if calls is not None:
            calls.append(kwargs)
        return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr=b"")

    return run


def test_availability_probe_strips_api_key_without_mutating_environ(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-user-key")
    monkeypatch.setattr(claude_login.shutil, "which", lambda _: "/usr/bin/claude")
    calls: list = []
    monkeypatch.setattr(claude_login.subprocess, "run", _fake_run(b'{"loggedIn": true}', calls=calls))

    assert claude_login.is_claude_cli_available() is True
    assert "ANTHROPIC_API_KEY" not in calls[0]["env"]
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-user-key"


def test_availability_probe_reports_logged_out(monkeypatch):
    monkeypatch.setattr(claude_login.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(claude_login.subprocess, "run", _fake_run(b'{"loggedIn": false}'))

    assert claude_login.is_claude_cli_available() is False


def test_availability_probe_without_binary(monkeypatch):
    monkeypatch.setattr(claude_login.shutil, "which", lambda _: None)

    assert claude_login.is_claude_cli_available() is False


@pytest.fixture
def cli(monkeypatch):
    """A logged-in CLI that counts how often it's started, and a clock the test moves."""
    calls: list = []
    now = {"t": 1000.0}
    monkeypatch.setattr(claude_login.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(claude_login.subprocess, "run", _fake_run(b'{"loggedIn": true}', calls=calls))
    monkeypatch.setattr(claude_login.time, "monotonic", lambda: now["t"])
    return calls, now


def test_the_status_is_checked_at_most_once_a_minute(cli):
    calls, now = cli
    assert [claude_login.is_claude_cli_available() for _ in range(5)] == [True] * 5
    assert len(calls) == 1

    now["t"] += 59
    claude_login.is_claude_cli_available()
    assert len(calls) == 1

    now["t"] += 2
    claude_login.is_claude_cli_available()
    assert len(calls) == 2


def test_a_login_change_is_checked_straight_away(cli, monkeypatch):
    calls, _ = cli
    assert claude_login.is_claude_cli_available() is True

    monkeypatch.setattr(claude_login.subprocess, "run", _fake_run(b'{"loggedIn": false}', calls=calls))
    claude_login.forget_cli_status()

    assert claude_login.is_claude_cli_available() is False
    assert len(calls) == 2


def test_a_check_begun_before_a_login_change_isnt_kept(cli, monkeypatch):
    calls, _ = cli
    real_run = claude_login.subprocess.run

    def run_then_change(args, **kwargs):
        result = real_run(args, **kwargs)
        claude_login.forget_cli_status()  # The login changed while this check ran.
        return result

    monkeypatch.setattr(claude_login.subprocess, "run", run_then_change)
    claude_login.is_claude_cli_available()
    monkeypatch.setattr(claude_login.subprocess, "run", real_run)
    claude_login.is_claude_cli_available()

    assert len(calls) == 2


def test_completing_a_login_checks_the_status_again(cli, monkeypatch):
    calls, _ = cli
    claude_login.is_claude_cli_available()

    class Process:
        returncode = 0

        async def communicate(self, input):
            return b"Logged in", b""

    monkeypatch.setattr(claude_login, "_pending", claude_login.PendingLogin(process=Process(), started_at=0.0))
    assert anyio.run(claude_login.complete_claude_login, "code") == (True, "Logged in")

    claude_login.is_claude_cli_available()
    assert len(calls) == 2
