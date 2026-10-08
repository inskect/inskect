"""Run one skillspector scan and report on stdout, one tagged JSON event per line.

This file can be copied to an isolated environment and run there on its own with
``python3 scan_runner.py <target> [--llm] [--baseline FILE] [--use-shipped-baseline]
[--yara-rules-dir DIR] [--transitive-depth N [--transitive-allow PREFIX]... [--transitive-deny PREFIX]...]``
(``--llm`` adds skillspector's AI review; ``--baseline`` suppresses the findings a baseline accepts;
``--use-shipped-baseline`` applies the one the skill ships, if any;
``--yara-rules-dir`` loads extra YARA rules; ``--transitive-depth`` follows the skill's external
references and scans them too), so it must stay standalone: the
standard library and skillspector only, nothing from ``app``. The API's own scans reuse its
baseline helpers.

Events, each on its own line after PREFIX:
- ``{"event": "start", "skillspector_version": "..."}``
- ``{"event": "step", "node": "..."}``: a graph node finished
- ``{"event": "log", "line": "INFO ..."}``: a skillspector log record
- ``{"event": "report", "report": {...}}``: the finished report, exit code 0. Its
  ``generated_baseline`` holds a baseline accepting every active finding, when one could be made;
  ``applied_baseline`` says which baseline suppressed findings ("uploaded" or "shipped"), and
  ``shipped_baseline`` whether the skill ships one, applied or not (see shipped_baseline)
  For a repository holding several skills, ``skills`` lists each skill's own report
  (see run_scan)
- ``{"event": "error", "message": "..."}``: the scan failed, exit code 1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, unquote, urlsplit

PREFIX = "@@inskect@@ "


def emit(event: str, **data: Any) -> None:
    sys.stdout.write(PREFIX + json.dumps({"event": event, **data}) + "\n")
    sys.stdout.flush()


class _EventLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        emit("log", line=self.format(record))


# Well under skillspector's own limit (2 MB): an uploaded baseline is stored with the scan, and each
# accepted finding is a few lines. A shipped one is held to the same.
MAX_BASELINE_BYTES = 256 * 1024


def baseline_state(path: str | None) -> dict[str, Any]:
    """The graph state that applies the baseline at path; nothing without one.

    Raises ValueError for a baseline skillspector can't load.
    """
    if path is None:
        return {}
    from skillspector.suppression import load_baseline

    return {"baseline": load_baseline(path), "show_suppressed": True}


def scan_report(final_state: dict[str, Any] | None) -> dict[str, Any]:
    """The finished report, with a baseline accepting each of its active findings.

    The baseline is made here because its exact fingerprints need the scanned files' contents,
    which only exist while the scan runs (skillspector's `skillspector baseline` does the same).
    """
    import skillspector
    from skillspector.suppression import build_baseline_dict, effective_findings

    final_state = final_state or {}
    report = json.loads(final_state.get("report_body") or "{}")
    findings = effective_findings(final_state)
    if findings:
        try:
            report["generated_baseline"] = build_baseline_dict(
                findings,
                file_cache=final_state.get("local_file_cache") or final_state.get("file_cache") or {},
                scanner_version=skillspector.__version__,
            )
        except ValueError:
            # Some findings can't be fingerprinted exactly (no source content); offer none.
            pass
    return report


# Repositories holding several skills: each folder with a SKILL.md, up to this deep, is scanned as
# a skill of its own (skillspector's own --recursive only looks one level down, at local folders).
MAX_SKILLS = 30
MAX_SKILL_DEPTH = 4
_SKIPPED_FOLDERS = {"node_modules", "venv", "__pycache__"}
# A skill isn't started with less time than this left before the deadline.
_MIN_SKILL_SECONDS = 20.0
_clock = time.monotonic
# Targets that are one file or archive: never several skills.
_FILE_SUFFIXES = {".md", ".zip", ".py", ".sh", ".js", ".ts", ".json", ".yaml", ".yml", ".txt"}


def _may_hold_several_skills(target: str) -> bool:
    parts = urlsplit(target)
    if not parts.scheme:
        return Path(target).is_dir()
    if parts.hostname == "raw.githubusercontent.com" or "/archive/" in parts.path:
        return False
    return PurePosixPath(parts.path).suffix.lower() not in _FILE_SUFFIXES


def find_skills(root: Path) -> list[Path]:
    """The folders under root holding a SKILL.md, outermost only; none when root is a skill itself.

    Hidden folders and symlinks are skipped, and the search stops past MAX_SKILLS + 1, so the caller
    can tell there were too many.
    """
    if (root / "SKILL.md").is_file():
        return []
    found: list[Path] = []
    for directory, folders, files in os.walk(root):
        here = Path(directory)
        depth = len(here.relative_to(root).parts)
        if depth and "SKILL.md" in files and not (here / "SKILL.md").is_symlink():
            found.append(here)
            folders[:] = []  # A skill's own subfolders are part of it.
            if len(found) > MAX_SKILLS:
                break
            continue
        keep = depth < MAX_SKILL_DEPTH
        folders[:] = sorted(f for f in folders if keep and not f.startswith(".") and f not in _SKIPPED_FOLDERS)
    return sorted(found)


def skill_name(folder: Path) -> str:
    """The `name:` in a SKILL.md's front matter, else the folder's name."""
    try:
        with open(folder / "SKILL.md", encoding="utf-8", errors="replace") as file:
            head = file.read(4096)
    except OSError:
        return folder.name
    if head.startswith("---"):
        for line in head.splitlines()[1:]:
            if line.strip() == "---":
                break
            key, _, value = line.partition(":")
            if key.strip() == "name" and value.strip():
                return value.strip().strip("\"'")[:100]
    return folder.name


def shipped_baseline(root: Path | None, *, use: bool, on_log: Callable[[str], None]) -> tuple[str | None, dict[str, Any] | None]:
    """The baseline the skill's author shipped at the top of root (skillspector's
    discover_baseline), and what the report says about it: (its path when it's to be applied,
    {"applied": ..., "problem": ...}); (None, None) when there's none.

    It's the author's own say on which findings don't count, so it's applied only when the user
    opted in (use), and checked like an uploaded one first. Never read when they didn't.
    """
    if root is None or not root.is_dir():
        return None, None
    from skillspector.suppression import SHIPPED_BASELINE_FILENAME

    candidate = root / SHIPPED_BASELINE_FILENAME
    # A link could point anywhere on this machine: it's not the skill's own file.
    if candidate.is_symlink() or not candidate.is_file():
        return None, None
    if not use:
        on_log(f"The skill ships a baseline ({SHIPPED_BASELINE_FILENAME}): not applied")
        return None, {"applied": False}
    problem = None
    if candidate.stat().st_size > MAX_BASELINE_BYTES:
        problem = f"it's larger than {MAX_BASELINE_BYTES // 1024} KB"
    else:
        try:
            baseline_state(str(candidate))
        except Exception as exc:  # noqa: BLE001 - the author's file: whatever's wrong with it, it's not applied
            problem = str(exc).replace(f": {candidate}", "").replace(str(candidate), "the file")
    if problem:
        on_log(f"The skill's shipped baseline can't be used: {problem}")
        return None, {"applied": False, "problem": problem}
    on_log(f"Applying the baseline the skill ships ({SHIPPED_BASELINE_FILENAME})")
    return str(candidate), {"applied": True}


def combine_reports(skills: list[dict[str, Any]], unscanned: list[dict[str, str]]) -> dict[str, Any]:
    """One report for a repository of several skills, with each skill's own under `skills`.

    The verdict is the riskiest skill's. Metadata is merged so AI review status and token usage
    read the same as for one skill, and the baseline accepts every skill's active findings.
    """
    reports = [entry["report"] for entry in skills if "report" in entry]
    if not reports:
        raise RuntimeError(next((entry["error"] for entry in skills if "error" in entry), "No skill could be inspected"))
    riskiest = max(reports, key=lambda report: report.get("risk_assessment", {}).get("score", 0))
    metas = [report.get("metadata") or {} for report in reports]
    metadata: dict[str, Any] = {
        "skillspector_version": metas[0].get("skillspector_version"),
        "llm_requested": any(meta.get("llm_requested") for meta in metas),
        "llm_available": all(meta.get("llm_available") for meta in metas),
        "meta_analysis_applied": all(meta.get("meta_analysis_applied") for meta in metas),
        "inference_usage": [record for meta in metas for record in meta.get("inference_usage") or []],
    }
    if any("llm_calls_attempted" in meta for meta in metas):
        metadata["llm_calls_attempted"] = sum(meta.get("llm_calls_attempted", 0) for meta in metas)
        metadata["llm_calls_succeeded"] = sum(meta.get("llm_calls_succeeded", 0) for meta in metas)
    if any(meta.get("llm_degraded") for meta in metas):
        metadata["llm_degraded"] = True
    errors = [meta["llm_error"] for meta in metas if meta.get("llm_error")]
    if errors:
        metadata["llm_error"] = errors[0]
    provenance = next((meta["llm_provenance"] for meta in metas if meta.get("llm_provenance")), None)
    if provenance:
        metadata["llm_provenance"] = provenance
    combined: dict[str, Any] = {
        # The page titles it from the target.
        "skill": {"name": "unknown", "source": "", "scanned_at": riskiest.get("skill", {}).get("scanned_at", "")},
        "risk_assessment": riskiest["risk_assessment"],
        "issues": [],
        "suppressed_count": sum(report.get("suppressed_count", 0) for report in reports),
        "execution_successful": len(reports) == len(skills)
        and not unscanned
        and all(report.get("execution_successful", True) for report in reports),
        "metadata": metadata,
        "skills": skills,
        "unscanned_skills": unscanned,
    }
    fingerprints = [
        entry for report in reports for entry in (report.get("generated_baseline") or {}).get("fingerprints", [])
    ]
    if fingerprints:
        first = next(report["generated_baseline"] for report in reports if report.get("generated_baseline"))
        combined["generated_baseline"] = {**first, "fingerprints": fingerprints}
    return combined


# skillspector's CLI, which alone implements following references (--transitive).
_CLI = "import sys; from skillspector.cli import app; sys.argv[0] = 'skillspector'; app()"
# A log line from an analyzer node, e.g. "INFO [skillspector.nodes.analyzers.static_yara] ...".
_NODE_LOG = re.compile(r"^(?:INFO|WARNING) \[skillspector\.nodes\.(?:analyzers\.)?(\w+)\]")


def _scan_with_cli(
    input_path: str,
    *,
    use_llm: bool,
    baseline_path: str | None,
    transitive: dict[str, Any],
    step: Callable[[str], None],
    on_log: Callable[[str], None],
    max_seconds: float | None = None,
    yara_rules_dir: str | None = None,
) -> dict[str, Any]:
    """Scan through skillspector's CLI, following references; its log stands in for graph steps."""
    from skillspector.graph import graph

    total_steps = len([node for node in graph.get_graph().nodes if node not in ("__start__", "__end__")])
    with tempfile.TemporaryDirectory() as directory:
        output = os.path.join(directory, "report.json")
        args = [sys.executable, "-c", _CLI, "scan", input_path, "--format", "json", "--output", output, "--verbose"]
        args += ["--transitive", "--transitive-depth", str(transitive["depth"])]
        for prefix in transitive.get("allow", []):
            args += ["--transitive-allow-prefix", prefix]
        for prefix in transitive.get("deny", []):
            args += ["--transitive-deny-prefix", prefix]
        if not use_llm:
            args.append("--no-llm")
        if baseline_path:
            args += ["--baseline", baseline_path]
        if yara_rules_dir:
            args += ["--yara-rules-dir", yara_rules_dir]
        env = dict(os.environ)
        if max_seconds is not None:
            env["SKILLSPECTOR_MAX_WORKFLOW_SECONDS"] = f"{max_seconds:g}"
        seen: set[str] = set()
        last_line = ""
        with subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, env=env) as process:
            assert process.stderr is not None
            for raw in process.stderr:
                line = raw.rstrip()
                if not line or line.startswith("DEBUG"):
                    continue
                last_line = line
                on_log(line)
                node = _NODE_LOG.match(line)
                if node and node.group(1) not in seen and len(seen) < total_steps:
                    seen.add(node.group(1))
                    step(node.group(1))
        # 0 and 1 (a risky skill) both mean a report was written; 2 is an error.
        if process.returncode not in (0, 1) or not os.path.exists(output):
            raise RuntimeError(re.sub(r"\[/?[a-z ]+\]", "", last_line) or f"skillspector exited with {process.returncode}")
        with open(output, encoding="utf-8") as file:
            return json.load(file)


# MCP servers, by their entry in the official MCP Registry: skillspector checks the entry's posture
# (pinned package versions and hashes, a repository, official status, plain-HTTP endpoints) rather
# than any code. Scanned by this URL, for the entry's latest version or a given one.
MCP_REGISTRY_HOST = "registry.modelcontextprotocol.io"
MCP_ENTRY_PREFIX = f"https://{MCP_REGISTRY_HOST}/v0/servers/"
MCP_POSTURE_CATEGORY = "MCP posture"
# What each posture rule's finding means, and what to do about it; skillspector only names the problem.
_MCP_RULE_TEXT = {
    "MCP-PACKAGE-VERSION": (
        "The registry entry gives a version range or a moving tag (such as latest), so what gets installed can change without the entry changing.",
        "Pin the package to an exact version in the server's registry entry.",
    ),
    "MCP-PACKAGE-SHA256": (
        "The package's fileSha256 isn't a SHA-256 digest, so the downloaded file can't be verified.",
        "Publish the SHA-256 digest of the package file in the registry entry.",
    ),
    "MCP-OFFICIAL-STATUS": (
        "The registry no longer lists this server as active: a deprecated or deleted server isn't maintained any more.",
        "Use an active server, or the replacement its publisher points to.",
    ),
    "MCP-PLAIN-HTTP": (
        "The remote endpoint is reached over plain HTTP, so traffic, credentials included, can be read or changed on the way.",
        "Connect to the server over HTTPS only.",
    ),
}
# skillspector's risk bands (skillspector/nodes/report.py), for a score skillspector sums itself.
_RISK_BANDS = ((81, "CRITICAL"), (51, "HIGH"), (21, "MEDIUM"), (0, "LOW"))
_RISK_RECOMMENDATION = {"LOW": "SAFE", "MEDIUM": "CAUTION", "HIGH": "DO_NOT_INSTALL", "CRITICAL": "DO_NOT_INSTALL"}
_SEVERITY_ORDER = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def is_mcp_entry(target: str) -> bool:
    return target.startswith(MCP_ENTRY_PREFIX)


def _fetch_mcp_entry(url: str) -> dict[str, Any]:
    import httpx
    from skillspector.mcp_registry import MAX_REGISTRY_BYTES

    name = unquote(url.removeprefix(MCP_ENTRY_PREFIX).split("/versions/")[0])
    try:
        response = httpx.get(url, timeout=30)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Couldn't reach the MCP Registry: {exc}") from exc
    if response.status_code == 404:
        raise RuntimeError(f"{name} isn't in the MCP Registry, or not at that version")
    if response.status_code != 200:
        raise RuntimeError(f"The MCP Registry answered {response.status_code} for {name}")
    if len(response.content) > MAX_REGISTRY_BYTES:
        raise RuntimeError(f"{name}'s registry entry is larger than {MAX_REGISTRY_BYTES // (1024 * 1024)} MB")
    try:
        entry = response.json()
    except ValueError as exc:
        raise RuntimeError(f"The MCP Registry's entry for {name} isn't JSON") from exc
    return entry


def scan_mcp_entry(url: str, *, on_step: Callable[[str], None], on_log: Callable[[str], None]) -> dict[str, Any]:
    """An MCP Registry entry's posture checks, as a report shaped like a skill's.

    Findings skillspector couldn't check (the entry leaves out what they need, such as a package's
    fileSha256) carry no risk: they're listed under mcp_server.unchecked rather than as issues.
    """
    import skillspector
    from skillspector.mcp_registry import normalize_payload, posture_findings

    on_log(f"Fetching the MCP Registry entry {url}")
    entry = _fetch_mcp_entry(url)
    on_step("fetch_registry_entry")
    try:
        (snapshot,) = normalize_payload({"servers": [entry]}, source=url)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    findings = posture_findings(snapshot)
    on_step("mcp_posture")
    on_log(f"Checked {snapshot.name} {snapshot.version or ''}".rstrip())

    issues: list[dict[str, Any]] = []
    unchecked: list[dict[str, str]] = []
    for finding in findings:
        if finding["evidence"] == "unavailable":
            unchecked.append({"id": finding["id"], "message": finding["message"], "target": finding["target"]})
            continue
        explanation, remediation = _MCP_RULE_TEXT.get(finding["id"], (finding["message"], ""))
        severity = finding["severity"].upper()
        issues.append(
            {
                "id": finding["id"],
                "finding_id": f"mcp-{len(issues) + 1}",
                "category": MCP_POSTURE_CATEGORY,
                "pattern": finding["message"],
                "severity": severity if severity in _SEVERITY_ORDER else "LOW",
                "confidence": 1.0,
                "finding": finding["target"],
                # What the finding is about (a package, an endpoint, the server) stands in for a file.
                "location": {"file": finding["target"], "start_line": 0, "end_line": None},
                "explanation": explanation,
                "remediation": remediation,
                "code_snippet": None,
                "intent": None,
                "tags": [MCP_POSTURE_CATEGORY],
                "evidence": {},
            }
        )
    score = min(sum(finding["risk_score"] for finding in findings), 100)
    band = next(band for threshold, band in _RISK_BANDS if score >= threshold)
    return {
        "skill": {"name": snapshot.name, "source": url, "scanned_at": snapshot.scanned_at},
        "risk_assessment": {
            "score": score,
            "severity": band,
            "recommendation": _RISK_RECOMMENDATION[band],
            "max_issue_severity": max((issue["severity"] for issue in issues), key=_SEVERITY_ORDER.index, default=None),
        },
        "issues": issues,
        "suppressed_count": 0,
        "suppressed": [],
        "metadata": {
            "skillspector_version": skillspector.__version__,
            "llm_requested": False,
            "llm_available": False,
            "meta_analysis_applied": False,
            "inference_usage": [],
        },
        "execution_successful": True,
        "mcp_server": {**snapshot.to_dict(), "unchecked": unchecked},
    }


# Folder links. skillspector clones a GitHub /tree/<ref>/<folder> link itself and scans the folder;
# GitLab's /-/tree/ and Hugging Face's /tree/ links are fetched here instead, within skillspector's
# own ingest limits, and the copy is scanned.
_HF_REPO_KINDS = {"spaces": "spaces", "datasets": "datasets"}


def _safe_segments(segments: list[str]) -> list[str]:
    if any(part in {"", ".", ".."} or "/" in part or "\\" in part for part in segments):
        raise RuntimeError("The folder link must stay within the repository")
    return segments


def _gitlab_folder(handler: Any, target: str) -> Path | None:
    """Clone a gitlab.com /-/tree/<ref>/<folder> link at its ref, as skillspector does GitHub's."""
    parts = urlsplit(target)
    segments = [unquote(part) for part in parts.path.split("/") if part]
    if parts.hostname != "gitlab.com" or "-" not in segments:
        return None
    marker = segments.index("-")
    if marker < 2 or segments[marker + 1 : marker + 2] != ["tree"] or len(segments) < marker + 3:
        return None
    repository_url = f"https://gitlab.com/{'/'.join(segments[:marker])}.git"
    rest = _safe_segments(segments[marker + 2 :])
    # skillspector's own: the longest branch or tag the link starts with is the ref, as refs may
    # hold slashes; and its clone, bounded by its ingest limits.
    try:
        ref, folder = handler._resolve_tree_ref(repository_url, rest)
    except ValueError as exc:
        raise RuntimeError(f"{'/'.join(rest)} doesn't start with a branch or tag of {repository_url}") from exc
    clone = handler._clone_git(repository_url, branch=ref).resolve()
    # Scanned as a plain folder, Git's own files would be scanned too.
    shutil.rmtree(clone / ".git", ignore_errors=True)
    path = (clone / PurePosixPath(*folder)).resolve()
    path.relative_to(clone)
    if not path.is_dir() or path.is_symlink():
        raise RuntimeError(f"{'/'.join(folder)} isn't a folder at {ref}")
    return path


def _huggingface_folder(handler: Any, target: str, on_log: Callable[[str], None]) -> Path | None:
    """Download a huggingface.co /tree/<ref>/<folder> link's files, listed by the Hub's API.

    Files stored with LFS (model weights and the like) are left out: they aren't a skill's code,
    and they're served from other hosts. Each file comes from /raw/, which serves it directly.
    """
    import httpx
    from skillspector.input_handler import (
        INGEST_MAX_BYTES,
        INGEST_MAX_SECONDS,
        INGEST_MAX_TREE_ENTRIES,
    )

    parts = urlsplit(target)
    raw = [part for part in parts.path.split("/") if part]
    if parts.hostname != "huggingface.co":
        return None
    kind = _HF_REPO_KINDS.get(raw[0], "models") if raw else "models"
    repo_end = 3 if kind != "models" else 2
    if len(raw) <= repo_end + 1 or raw[repo_end] != "tree":
        return None
    repo = "/".join(raw[:repo_end])  # As linked, with spaces/ or datasets/ in front.
    api_repo = "/".join(raw[1:repo_end] if kind != "models" else raw[:repo_end])
    # A ref with slashes (refs/pr/1) is linked encoded, so it's one segment.
    ref = unquote(raw[repo_end + 1])
    folder = _safe_segments([unquote(part) for part in raw[repo_end + 2 :]])
    deadline = time.monotonic() + INGEST_MAX_SECONDS

    def get(url: str, **options: Any) -> httpx.Response:
        if time.monotonic() > deadline:
            raise RuntimeError(f"Fetching the folder took longer than {INGEST_MAX_SECONDS:g} seconds")
        try:
            return httpx.get(url, timeout=30, follow_redirects=False, **options)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Couldn't reach Hugging Face: {exc}") from exc

    folder_path = "".join(f"/{quote(part, safe='')}" for part in folder)
    listing = get(f"https://huggingface.co/api/{kind}/{api_repo}/tree/{quote(ref, safe='')}{folder_path}", params={"recursive": "true"})
    if listing.status_code == 404:
        raise RuntimeError(f"{'/'.join(folder) or 'The folder'} isn't in {repo} at {ref}")
    if listing.status_code != 200:
        raise RuntimeError(f"Hugging Face answered {listing.status_code} listing the folder")
    # The Hub pages long listings; one this long is past the limit anyway.
    if listing.headers.get("link"):
        raise RuntimeError(f"The folder holds more than {INGEST_MAX_TREE_ENTRIES} entries")
    files = [entry for entry in listing.json() if entry.get("type") == "file"]
    skipped = [entry for entry in files if entry.get("lfs")]
    files = [entry for entry in files if not entry.get("lfs")]
    if len(files) > INGEST_MAX_TREE_ENTRIES:
        raise RuntimeError(f"The folder holds more than {INGEST_MAX_TREE_ENTRIES} files")
    if sum(int(entry.get("size") or 0) for entry in files) > INGEST_MAX_BYTES:
        raise RuntimeError(f"The folder is larger than {INGEST_MAX_BYTES // (1024 * 1024)} MB")
    if skipped:
        on_log(f"Skipped {len(skipped)} large file{'s' if len(skipped) != 1 else ''} stored with LFS")

    root = handler._get_temp_dir() / "folder"
    root.mkdir()
    prefix = "/".join(folder)
    total = 0
    for entry in files:
        path = str(entry["path"])
        relative = _safe_segments(path.removeprefix(prefix).strip("/").split("/")) if prefix else _safe_segments(path.split("/"))
        response = get(f"https://huggingface.co/{repo}/raw/{quote(ref, safe='')}/{quote(path)}")
        if response.status_code != 200:
            raise RuntimeError(f"Hugging Face answered {response.status_code} for {path}")
        total += len(response.content)
        if total > INGEST_MAX_BYTES:
            raise RuntimeError(f"The folder is larger than {INGEST_MAX_BYTES // (1024 * 1024)} MB")
        destination = root.joinpath(*relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)
    if not files:
        raise RuntimeError(f"{'/'.join(folder) or 'The folder'} holds no files to inspect")
    return root


def fetch_folder(handler: Any, target: str, on_log: Callable[[str], None]) -> Path | None:
    """A local copy of a GitLab or Hugging Face folder link, to scan in its place; None for any other target."""
    return _gitlab_folder(handler, target) or _huggingface_folder(handler, target, on_log)


def run_scan(
    target: str,
    *,
    use_llm: bool,
    baseline_path: str | None = None,
    use_shipped_baseline: bool = False,
    on_step: Callable[[str], None],
    on_log: Callable[[str], None],
    config: dict[str, Any] | None = None,
    deadline_seconds: float | None = None,
    transitive: dict[str, Any] | None = None,
    yara_rules_dir: str | None = None,
) -> dict[str, Any]:
    """Scan target, splitting a repository that holds several skills into one scan per skill.

    on_step is called once per graph step of a single scan; for several skills, as many times
    spread over all of them, so progress still ends at the graph's step count. With
    deadline_seconds, skills are only started while there's time left for them. With transitive
    ({"depth", "allow", "deny"}), each scan also follows the skill's external references; it runs
    through skillspector's CLI, so it makes no baseline (that needs the scanned files' contents).
    yara_rules_dir adds a directory of YARA rules to skillspector's own. A baseline the skill ships
    at its top is applied with use_shipped_baseline, unless baseline_path gives one (as
    skillspector's CLI does); the report says it was found either way. An MCP Registry entry's URL
    is checked by scan_mcp_entry instead, which none of these options apply to.
    """
    if is_mcp_entry(target):
        return scan_mcp_entry(target, on_step=on_step, on_log=on_log)
    from skillspector.graph import graph

    base_state: dict[str, Any] = {"output_format": "json", "use_llm": use_llm, **baseline_state(baseline_path)}
    if yara_rules_dir:
        base_state["yara_rules_dir"] = yara_rules_dir
    applied = "uploaded" if baseline_path else None
    shipped: dict[str, Any] | None = None

    def scan_one(input_path: str, step: Callable[[str], None], extra: dict[str, Any] | None = None) -> dict[str, Any]:
        if transitive:
            budget = (extra or {}).get("workflow_resource_budget")
            return _scan_with_cli(
                input_path,
                use_llm=use_llm,
                baseline_path=baseline_path,
                transitive=transitive,
                step=step,
                on_log=on_log,
                max_seconds=budget.max_seconds if budget is not None else None,
                yara_rules_dir=yara_rules_dir,
            )
        final_state: dict[str, Any] | None = None
        for mode, chunk in graph.stream({**base_state, "input_path": input_path, **(extra or {})}, config=config, stream_mode=["updates", "values"]):
            if mode == "updates":
                for node_name in chunk:
                    step(node_name)
            elif mode == "values":
                final_state = chunk
        return scan_report(final_state)

    started = _clock()
    skills: list[Path] = []
    root: Path | None = None
    handler = None
    copy: Path | None = None
    try:
        if _may_hold_several_skills(target):
            from skillspector.input_handler import InputHandler

            handler = InputHandler()
            copy = fetch_folder(handler, target, on_log)
            try:
                root = copy or handler.resolve(target)[0]
                skills = find_skills(root) if root.is_dir() else []
            except Exception:  # noqa: BLE001
                # The scan itself reports a target it can't fetch, as before.
                root, skills = None, []
            # An uploaded baseline wins, as with skillspector's CLI; the shipped one is still noted.
            shipped_path, shipped = shipped_baseline(root, use=use_shipped_baseline and baseline_path is None, on_log=on_log)
            if shipped_path is not None:
                # Read by scan_one when it runs.
                baseline_path, applied = shipped_path, "shipped"
                base_state.update(baseline_state(shipped_path))
        if len(skills) < 2:
            # Following references, skillspector's CLI charges the target's own download to the
            # traversal's 10 MB budget, which one repository clone can use up: scan the copy
            # fetched above instead, so the budget goes to what the skill references. A folder
            # fetched here can only be scanned from its copy.
            report = scan_one(str(root) if root is not None and (transitive or copy) else target, on_step)
        elif len(skills) > MAX_SKILLS:
            raise RuntimeError(f"This repository holds more than {MAX_SKILLS} skills: inspect them one folder at a time")
        else:
            report = _scan_each(root, skills, scan_one, on_step, on_log, started, deadline_seconds)
        if applied:
            report["applied_baseline"] = applied
        if shipped is not None:
            report["shipped_baseline"] = shipped
        return report
    finally:
        if handler is not None:
            handler.cleanup()


def _scan_each(root, skills, scan_one, on_step, on_log, started, deadline_seconds) -> dict[str, Any]:
    from skillspector.graph import graph
    from skillspector.state import WorkflowResourceBudget

    total_steps = len([node for node in graph.get_graph().nodes if node not in ("__start__", "__end__")])
    emitted = 0
    entries: list[dict[str, Any]] = []
    unscanned: list[dict[str, str]] = []
    on_log(f"Found {len(skills)} skills: scanning each one")
    for index, folder in enumerate(skills):
        path, name = folder.relative_to(root).as_posix(), skill_name(folder)
        extra: dict[str, Any] = {}
        if deadline_seconds is not None:
            remaining = deadline_seconds - (_clock() - started)
            if remaining < _MIN_SKILL_SECONDS:
                unscanned.append({"path": path, "name": name, "reason": "The scan ran out of time before this skill"})
                continue
            # A fair share of what's left, so one large skill can't use up every other skill's time:
            # it ends partly inspected instead, and says so.
            share = max(remaining / (len(skills) - index), _MIN_SKILL_SECONDS)
            extra["workflow_resource_budget"] = WorkflowResourceBudget(max_seconds=min(share, remaining))
        on_log(f"Scanning skill {index + 1} of {len(skills)}: {path}")
        done = 0

        def step(node_name: str, index: int = index) -> None:
            nonlocal done, emitted
            done = min(done + 1, total_steps)
            # Progress over every skill, scaled to one scan's step count.
            while emitted < (index * total_steps + done) // len(skills):
                emitted += 1
                on_step(node_name)

        try:
            entries.append({"path": path, "name": name, "report": scan_one(str(folder), step, extra)})
        except Exception as exc:  # noqa: BLE001
            on_log(f"Skill {path} failed: {exc}")
            entries.append({"path": path, "name": name, "error": str(exc)})
    return combine_reports(entries, unscanned)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="scan_runner.py")
    parser.add_argument("target")
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--baseline")
    parser.add_argument("--use-shipped-baseline", action="store_true")
    parser.add_argument("--yara-rules-dir")
    parser.add_argument("--transitive-depth", type=int)
    parser.add_argument("--transitive-allow", action="append", default=[])
    parser.add_argument("--transitive-deny", action="append", default=[])
    try:
        args = parser.parse_args(argv[1:])
    except SystemExit:
        return 2
    target, use_llm = args.target, args.llm

    import skillspector

    # Attached after the import, like the API does, so only this scan's records are reported.
    handler = _EventLogHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger = logging.getLogger("skillspector")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    emit("start", skillspector_version=skillspector.__version__)
    # Whoever runs this file may set skillspector's deadline under its own limit; several skills
    # share it.
    deadline = os.environ.get("SKILLSPECTOR_MAX_WORKFLOW_SECONDS")
    try:
        report = run_scan(
            target,
            use_llm=use_llm,
            baseline_path=args.baseline,
            use_shipped_baseline=args.use_shipped_baseline,
            on_step=lambda node: emit("step", node=node),
            on_log=lambda line: emit("log", line=line),
            deadline_seconds=float(deadline) if deadline else None,
            yara_rules_dir=args.yara_rules_dir,
            transitive={"depth": args.transitive_depth, "allow": args.transitive_allow, "deny": args.transitive_deny}
            if args.transitive_depth
            else None,
        )
        emit("report", report=report)
        return 0
    except Exception as exc:  # noqa: BLE001
        emit("error", message=str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
