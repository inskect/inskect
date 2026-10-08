from __future__ import annotations

import email
import os
import socketserver
import threading
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

from app.core.config import AnalysisSettings, Settings, get_settings

# Tests never read the developer's .env / .env.local: those can hold real SMTP or API credentials,
# and a test must never send a real email or call a real provider with them.
Settings.model_config["env_file"] = ()
AnalysisSettings.model_config["env_file"] = ()
get_settings.cache_clear()

# Imported only now, so nothing has cached settings read from the real files.
from app import db

# Point this at a throwaway Postgres database to run every storage test on both engines.
# Its tables are dropped before each test.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _worker_database(url: str, worker: str) -> str:
    """A database of its own for one pytest-xdist worker, next to url's, created if need be: each
    test drops every table, which would pull them from under the other workers' tests."""
    import psycopg
    from psycopg import sql

    parts = urlsplit(url)
    name = f"{parts.path.lstrip('/') or 'postgres'}_{worker}"
    with psycopg.connect(url, autocommit=True) as conn:
        if conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone() is None:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    return urlunsplit(parts._replace(path=f"/{name}"))


if TEST_DATABASE_URL and (worker := os.environ.get("PYTEST_XDIST_WORKER")):
    TEST_DATABASE_URL = _worker_database(TEST_DATABASE_URL, worker)
    # For the test modules that read it themselves.
    os.environ["TEST_DATABASE_URL"] = TEST_DATABASE_URL


def _reset_postgres(url: str) -> None:
    import psycopg

    with psycopg.connect(url, autocommit=True) as conn:
        # Every table, including ones added by later migrations, without listing them here.
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")


@pytest.fixture(
    params=[
        "sqlite",
        pytest.param(
            "postgres",
            marks=pytest.mark.skipif(not TEST_DATABASE_URL, reason="set TEST_DATABASE_URL to test Postgres"),
        ),
    ]
)
def temp_db(request, tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "scan_retention_days", None)
    # On Postgres too: local uploads live next to it (app/uploads.py), so a test never touches a
    # real data/uploads folder, or leaves one behind for the next test.
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "test.db"))
    if request.param == "postgres":
        _reset_postgres(TEST_DATABASE_URL)
        monkeypatch.setattr(settings, "database_url", TEST_DATABASE_URL)
    else:
        monkeypatch.setattr(settings, "database_url", None)
    db.init_db()
    yield request.param
    db.close_db()


class FakeRunner:
    """A job runner that records submitted scans instead of running them."""

    def __init__(self) -> None:
        self.submitted = []
        self.full = False
        self.rejection: str | None = None

    def on_startup(self) -> None:
        return None

    def is_full(self) -> bool:
        return self.full

    def check(self, llm) -> None:
        if self.rejection:
            from app.jobs import JobRejectedError

            raise JobRejectedError(self.rejection)

    async def submit(self, job) -> None:
        self.submitted.append(job)


@pytest.fixture
def fake_runner(monkeypatch):
    from app.api.routes import scan as scan_routes

    runner = FakeRunner()
    monkeypatch.setattr(scan_routes, "get_runner", lambda: runner)
    return runner


@pytest.fixture(autouse=True)
def _fresh_proxy_warning():
    from app import proxy

    proxy.reset()
    yield
    proxy.reset()


@pytest.fixture(autouse=True)
def _fresh_claude_cli_status():
    """The Claude CLI's status, cached for a minute, is checked afresh in every test."""
    from app import claude_login

    claude_login.forget_cli_status()
    yield
    claude_login.forget_cli_status()


@pytest.fixture(autouse=True)
def _fresh_comparisons():
    """Comparisons cached by one test's scans never answer another's, which may reuse their ids."""
    from app import rescan

    rescan.clear_cache()
    yield
    rescan.clear_cache()


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    """Every test starts with no hits counted, and the limiter re-reads the settings."""
    from app import rate_limit

    rate_limit.reset()
    yield
    rate_limit.reset()


CANARY_RULE = """rule acme_canary
{
    meta:
        description = "Mentions the ACME canary"
    strings:
        $a = "acme-canary-7c1f"
    condition:
        $a
}
"""


@pytest.fixture
def yara_rules_dir(tmp_path) -> Path:
    """An operator's extra YARA rules: one matching skills that mention the ACME canary."""
    path = tmp_path / "operator-rules"
    (path / "acme").mkdir(parents=True)
    (path / "acme" / "canary.yar").write_text(CANARY_RULE)
    (path / "README.md").write_text("Not a rule")
    return path


class _SMTPHandler(socketserver.StreamRequestHandler):
    """Just enough SMTP to accept a message: tests the mailer over the real protocol."""

    def _reply(self, line: str) -> None:
        self.wfile.write(f"{line}\r\n".encode())

    def handle(self) -> None:
        self._reply("220 test ESMTP")
        while line := self.rfile.readline():
            command = line.decode().strip().upper()
            if command.startswith(("EHLO", "HELO")):
                self._reply("250 test")
            elif command.startswith(("MAIL FROM", "RCPT TO", "RSET", "NOOP")):
                self._reply("250 OK")
            elif command == "DATA":
                self._reply("354 go ahead")
                data = b""
                while (chunk := self.rfile.readline()) != b".\r\n":
                    data += chunk
                self.server.messages.append(email.message_from_bytes(data))
                self._reply("250 queued")
            elif command == "QUIT":
                self._reply("221 bye")
                return
            else:
                self._reply("502 not implemented")


@pytest.fixture
def smtp(monkeypatch):
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _SMTPHandler)
    server.messages = []
    # A short poll, so shutting it down after each test doesn't wait half a second.
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "smtp_port", server.server_address[1])
    monkeypatch.setattr(settings, "smtp_security", "none")
    monkeypatch.setattr(settings, "mail_from", "Inskect <noreply@example.com>")
    monkeypatch.setattr(settings, "public_url", "https://inskect.example.com/")
    yield server.messages
    server.shutdown()
