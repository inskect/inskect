"""What changed since a target's previous scan: findings new, fixed and unchanged.

Scans are compared with the latest earlier one of the same target, by the same owner, that finished,
and of the same kind (with AI review or without: comparing one with the other would report the AI's
findings as fixed or new). That previous scan is looked up when a result is read, so deleting a scan
or rescanning while another is running needs no bookkeeping.

skillspector's finding ids change between runs, so findings are matched by a key that doesn't: the
skill they're in (for a repository holding several), the file, the rule, and skillspector's own
match_fingerprint (a digest of the rule and the matched text, whitespace normalized). Findings
without one, as AI review's can be, fall back to their text. Line numbers aren't part of the key:
editing above a finding moves it without changing it.
"""

from __future__ import annotations

import hashlib
import threading
from collections import Counter, OrderedDict
from typing import Any

from app import db


def _issues(result: dict[str, Any] | None) -> list[tuple[str | None, dict[str, Any]]]:
    """Every active finding of a report, with the path of the skill it's in for several."""
    result = result or {}
    if result.get("skills"):
        return [
            (entry.get("path"), issue)
            for entry in result["skills"]
            for issue in (entry.get("report") or {}).get("issues") or []
        ]
    return [(None, issue) for issue in result.get("issues") or []]


def finding_key(issue: dict[str, Any], skill_path: str | None = None) -> str:
    match = issue.get("match_fingerprint")
    if not match:
        text = issue.get("finding") or issue.get("pattern") or issue.get("explanation") or ""
        match = "text:" + " ".join(str(text).split())
    location = issue.get("location") or {}
    parts = [skill_path or "", location.get("file") or "", issue.get("id") or "", match]
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def compare(previous: dict[str, Any], current: dict[str, Any]) -> tuple[dict[str, Any], Counter[str]]:
    """The comparison of current's report with previous's, and how many of each finding previous had
    (for mark_changes).

    A rule matching the same text twice in a file counts twice: one of them gone is one fixed.
    """
    before = Counter(finding_key(issue, path) for path, issue in _issues(previous.get("result")))
    after = Counter(finding_key(issue, path) for path, issue in _issues(current.get("result")))

    fixed: list[dict[str, Any]] = []
    remaining = before - after
    for path, issue in _issues(previous.get("result")):
        key = finding_key(issue, path)
        if remaining[key] > 0:
            remaining[key] -= 1
            fixed.append({**issue, "skill_path": path} if path else issue)

    risk = ((previous.get("result") or {}).get("risk_assessment")) or {}
    return {
        "previous": {
            "id": previous["id"],
            "created_at": previous["created_at"],
            "risk_score": risk.get("score"),
            "severity": risk.get("severity"),
            "recommendation": risk.get("recommendation"),
        },
        "new_count": sum((after - before).values()),
        "unchanged_count": sum((after & before).values()),
        "fixed": fixed,
    }, before


# Comparisons already made, by both scans' id and when they finished: a finished report doesn't
# change (run again, a scan finishes anew), and a result page reads its scan every few seconds.
# Callers copy what they change (mark_changes), so the cached values are shared as they are.
_CACHE_SIZE = 64
_cache: OrderedDict[tuple[Any, ...], tuple[dict[str, Any], Counter[str]] | None] = OrderedDict()
_cache_lock = threading.Lock()


def comparison_for(scan: dict[str, Any]) -> tuple[dict[str, Any], Counter[str]] | None:
    """The comparison with the scan's previous one, when it's done and has one. Looks up which scan
    that is, and loads its report only when the comparison isn't cached already."""
    if scan.get("status") != "done" or not scan.get("result"):
        return None
    ref = db.previous_scan(
        target=scan["target"],
        owner_id=scan.get("owner_id"),
        before=scan["created_at"],
        with_ai_review=scan.get("provider") is not None,
        columns="id, finished_at",
    )
    if ref is None:
        return None
    key = (scan["id"], scan.get("finished_at"), ref["id"], ref["finished_at"])
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    previous = db.get_scan(ref["id"])
    compared = compare(previous, scan) if previous is not None and previous.get("result") else None
    with _cache_lock:
        _cache[key] = compared
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return compared


def clear_cache() -> None:
    """Forget every comparison made (for tests)."""
    with _cache_lock:
        _cache.clear()


def mark_changes(issues: list[dict[str, Any]], before: Counter[str], skill_path: str | None = None) -> list[dict[str, Any]]:
    """Copies of a report's findings, each marked new or unchanged since the previous scan, which had
    `before` of each. Past that many, the same finding again is a new one."""
    left = before.copy()
    marked = []
    for issue in issues:
        key = finding_key(issue, skill_path)
        seen = left[key] > 0
        left[key] -= 1
        marked.append({**issue, "change": "unchanged" if seen else "new"})
    return marked
