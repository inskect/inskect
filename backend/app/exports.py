"""A scan's report to download: as skillspector's own JSON, or as SARIF 2.1.0 for code scanning tools.

The SARIF is skillspector's own (what `skillspector scan --format sarif` writes), rebuilt from the
stored report: its findings are turned back into skillspector's Finding objects and handed to its
SARIF writer. A repository holding several skills becomes one SARIF run, each finding's file
prefixed with its skill's folder, so paths stay relative to the repository.
"""

from __future__ import annotations

import json
import re
from typing import Any

SARIF_MEDIA_TYPE = "application/sarif+json"


def _finding(issue: dict[str, Any], skill_path: str | None = None) -> Any:
    from skillspector.models import Finding

    prefix = f"{skill_path}/" if skill_path else ""
    location = issue.get("location") or {}

    def place(raw: dict[str, Any]) -> dict[str, Any]:
        # SARIF lines start at 1; a finding about something other than a file (an MCP server's
        # package) has none.
        return {**raw, "file": prefix + str(raw.get("file") or ""), "start_line": max(int(raw.get("start_line") or 1), 1)}

    fields = {
        "rule_id": issue.get("id") or "",
        # The report keeps the analyzer's message as the explanation when it has no other.
        "message": issue.get("explanation") or issue.get("pattern") or issue.get("id") or "",
        "finding_id": issue.get("finding_id") or "",
        "severity": issue.get("severity") or "LOW",
        "confidence": float(issue.get("confidence") or 0.5),
        "file": prefix + str(location.get("file") or ""),
        "start_line": max(int(location.get("start_line") or 1), 1),
        "end_line": location.get("end_line"),
        "start_column": location.get("start_column"),
        "end_column": location.get("end_column"),
        "category": issue.get("category"),
        "pattern": issue.get("pattern"),
        "finding": issue.get("finding"),
        "explanation": issue.get("explanation"),
        "remediation": issue.get("remediation"),
        "code_snippet": issue.get("code_snippet"),
        "intent": issue.get("intent"),
        "tags": list(issue.get("tags") or []),
        "transitive_depth": int(issue.get("transitive_depth") or 0),
        "source_url": issue.get("source_url"),
        "source_identity": issue.get("source_identity"),
        "source_digest": issue.get("source_digest"),
        "evidence": dict(issue.get("evidence") or {}),
        "match_fingerprint": issue.get("match_fingerprint"),
        "occurrences": [place(raw) for raw in issue.get("occurrences") or [] if isinstance(raw, dict)],
    }
    return Finding(**fields)


def _reports(result: dict[str, Any]) -> list[tuple[str | None, dict[str, Any]]]:
    if result.get("skills"):
        return [(entry.get("path"), entry["report"]) for entry in result["skills"] if entry.get("report")]
    return [(None, result)]


def sarif(result: dict[str, Any]) -> dict[str, Any]:
    """The report as a SARIF 2.1.0 log, validated by skillspector's own SARIF models."""
    from skillspector.nodes.report import _build_sarif
    from skillspector.sarif_models import validate_sarif_report
    from skillspector.suppression import SuppressedFinding

    findings, suppressed = [], []
    for path, report in _reports(result):
        findings += [_finding(issue, path) for issue in report.get("issues") or []]
        suppressed += [
            SuppressedFinding(finding=_finding(entry, path), reason=str(entry.get("suppression_reason") or entry.get("reason") or "accepted in the baseline"))
            for entry in report.get("suppressed") or []
        ]
    log = _build_sarif(
        findings,
        suppressed=suppressed,
        analysis_completeness=result.get("analysis_completeness"),
        execution_successful=bool(result.get("execution_successful", True)),
        structured_summaries=result.get("structured_summaries"),
    )
    validate_sarif_report(log)
    return log


def filename(target: str, extension: str) -> str:
    """A download's name, after what was scanned: inskect-<target>.<extension>."""
    name = target.removeprefix("upload:").split("://", 1)[-1]
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")[:80] or "report"
    return f"inskect-{name}.{extension}"


def as_bytes(document: dict[str, Any]) -> bytes:
    return json.dumps(document, indent=2, ensure_ascii=False).encode()
