from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import scan_runner, scanner
from app.main import app
from app.scan_runner import PREFIX
from app.targets import mcp_entry_url

ENTRY_URL = "https://registry.modelcontextprotocol.io/v0/servers/io.github.acme%2Fweather/versions/latest"


def _entry(**server) -> dict:
    return {
        "server": {
            "name": "io.github.acme/weather",
            "version": "1.2.0",
            "repository": {"url": "https://github.com/acme/weather", "source": "github"},
            "packages": [{"registryType": "npm", "identifier": "@acme/weather", "version": "latest", "transport": {"type": "stdio"}}],
            **server,
        },
        "_meta": {"io.modelcontextprotocol.registry/official": {"status": "active", "isLatest": True}},
    }


@pytest.fixture
def registry(monkeypatch):
    """Stands in for the MCP Registry: serves `entries` by URL, and records what was asked for."""
    entries: dict[str, dict] = {ENTRY_URL: _entry()}
    requested: list[str] = []

    def get(url, **_options):
        requested.append(url)
        if url not in entries:
            return httpx.Response(404, json={"title": "Not Found"}, request=httpx.Request("GET", url))
        return httpx.Response(200, json=entries[url], request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get)
    return entries, requested


@pytest.mark.parametrize(
    ("target", "url"),
    [
        ("io.github.acme/weather", ENTRY_URL),
        ("https://registry.modelcontextprotocol.io/v0/servers/io.github.acme%2Fweather/versions/latest", ENTRY_URL),
        # Another API version, and a given version, are scanned as linked.
        (
            "https://registry.modelcontextprotocol.io/v0.1/servers/io.github.acme%2Fweather/versions/1.0.0",
            "https://registry.modelcontextprotocol.io/v0/servers/io.github.acme%2Fweather/versions/1.0.0",
        ),
        # A server without a version means its latest.
        ("https://registry.modelcontextprotocol.io/v0/servers/io.github.acme%2Fweather", ENTRY_URL),
        # A GitHub-style owner/repo isn't a server name: its namespace has no dot.
        ("anthropics/skills", None),
        ("https://github.com/acme/weather", None),
        ("https://registry.modelcontextprotocol.io/v0/servers", None),
        ("https://evil.example/v0/servers/io.github.acme%2Fweather/versions/latest", None),
    ],
)
def test_mcp_servers_are_scanned_by_their_registry_entry(target, url):
    assert mcp_entry_url(target) == url


def test_an_unpinned_package_reports_mcp_package_version(registry):
    report = scan_runner.scan_mcp_entry(ENTRY_URL, on_step=lambda node: None, on_log=lambda line: None)

    (issue,) = report["issues"]
    assert issue["id"] == "MCP-PACKAGE-VERSION"
    assert issue["severity"] == "HIGH"
    assert issue["location"]["file"] == "@acme/weather"
    assert issue["remediation"]
    assert report["risk_assessment"] == {"score": 30, "severity": "MEDIUM", "recommendation": "CAUTION", "max_issue_severity": "HIGH"}
    assert report["skill"]["name"] == "io.github.acme/weather"
    # What the entry leaves out isn't a finding, but the report says it wasn't checked.
    assert report["mcp_server"]["unchecked"] == [
        {"id": "MCP-PACKAGE-SHA256", "message": "Package fileSha256 is unavailable", "target": "@acme/weather"}
    ]
    assert report["mcp_server"]["packages"][0]["identifier"] == "@acme/weather"


def test_a_well_kept_entry_is_safe(registry):
    entries, _ = registry
    package = {"registryType": "npm", "identifier": "@acme/weather", "version": "1.2.0", "fileSha256": "a" * 64}
    entries[ENTRY_URL] = _entry(packages=[package], remotes=[{"type": "streamable-http", "url": "https://mcp.acme.dev"}])

    report = scan_runner.scan_mcp_entry(ENTRY_URL, on_step=lambda node: None, on_log=lambda line: None)

    assert report["issues"] == []
    assert report["mcp_server"]["unchecked"] == []
    assert report["risk_assessment"]["recommendation"] == "SAFE"


def test_plain_http_and_a_deprecated_server_are_findings(registry):
    entries, _ = registry
    entry = _entry(packages=[], remotes=[{"type": "sse", "url": "http://mcp.acme.dev/sse"}])
    entry["_meta"]["io.modelcontextprotocol.registry/official"]["status"] = "deprecated"
    entries[ENTRY_URL] = entry

    report = scan_runner.scan_mcp_entry(ENTRY_URL, on_step=lambda node: None, on_log=lambda line: None)

    assert {(issue["id"], issue["finding"]) for issue in report["issues"]} == {
        ("MCP-OFFICIAL-STATUS", "io.github.acme/weather"),
        ("MCP-PLAIN-HTTP", "http://mcp.acme.dev/sse"),
    }
    assert report["risk_assessment"]["score"] == 45


def test_a_server_missing_from_the_registry_says_so(registry):
    url = ENTRY_URL.replace("weather", "nothing")

    with pytest.raises(RuntimeError, match="io.github.acme/nothing isn't in the MCP Registry"):
        scan_runner.scan_mcp_entry(url, on_step=lambda node: None, on_log=lambda line: None)


def test_a_local_scan_checks_the_entry(registry):
    report = scanner._invoke_graph("s", ENTRY_URL, False)

    assert [issue["id"] for issue in report["issues"]] == ["MCP-PACKAGE-VERSION"]


def test_the_scan_runner_checks_the_entry(registry, capsys):
    assert scan_runner.main(["scan_runner.py", ENTRY_URL]) == 0

    events = [json.loads(line[len(PREFIX) :]) for line in capsys.readouterr().out.splitlines() if line.startswith(PREFIX)]
    (report,) = [event["report"] for event in events if event["event"] == "report"]
    assert [issue["id"] for issue in report["issues"]] == ["MCP-PACKAGE-VERSION"]


@pytest.fixture
def client(temp_db, fake_runner):
    client = TestClient(app)
    client.scheduled = fake_runner.submitted
    return client


def test_a_server_name_is_queued_as_its_registry_entry(client):
    response = client.post("/scan", json={"target": " io.github.acme/weather "})

    assert response.status_code == 200
    assert client.scheduled[0].target == ENTRY_URL


@pytest.mark.parametrize(
    "options",
    [{"baseline": "version: 2"}, {"transitive_depth": 1}, {"llm": {"provider": "anthropic", "api_key": "sk-ant-x"}}],
)
def test_options_for_code_are_refused_for_an_mcp_server(client, options):
    response = client.post("/scan", json={"target": "io.github.acme/weather", **options})

    assert response.status_code == 422
    assert "registry entry only" in response.json()["detail"]
    assert client.scheduled == []
