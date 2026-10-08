from __future__ import annotations

from typing import Any, Protocol

from app.ai_review import ai_review_status
from app.ai_usage import token_totals

# A scan as a plain dict keyed by column name, with `result` already decoded from JSON.
ScanRow = dict[str, Any]

# Columns `list_scans` returns: everything except the (large) result.
SUMMARY_COLUMNS = (
    "id, target, status, created_at, finished_at, error, risk_score, severity, recommendation, ai_review, owner_id, "
    "provider, completed_steps, report_no"
)


def scan_filter(placeholder: str, *, owner_id: str | None, target: str | None) -> tuple[str, tuple[Any, ...]]:
    """The WHERE clause for listing scans, optionally only one user's or one target's."""
    clauses, params = [], []
    if owner_id is not None:
        clauses.append(f"owner_id = {placeholder}")
        params.append(owner_id)
    if target is not None:
        clauses.append(f"target = {placeholder}")
        params.append(target)
    return ("WHERE " + " AND ".join(clauses) if clauses else ""), tuple(params)


# How the history can be sorted (GET /scan?sort=…&order=…): each key's SQL, from this list only.
# A verdict sorts by how risky it is; scans without a score or a verdict yet (failed, or still
# running) come last whichever way, and ties go newest first, so pages never overlap.
SCAN_SORTS = {
    "created_at": "created_at",
    "target": "target",
    "risk_score": "risk_score",
    "verdict": "CASE recommendation WHEN 'DO_NOT_INSTALL' THEN 3 WHEN 'CAUTION' THEN 2 WHEN 'SAFE' THEN 1 END",
    "status": "status",
}


def scan_order(sort: str = "created_at", order: str = "desc") -> str:
    """The ORDER BY clause for listing scans; unknown keys fall back to newest first."""
    column = SCAN_SORTS.get(sort, "created_at")
    direction = "ASC" if order == "asc" else "DESC"
    return f"ORDER BY {column} {direction} NULLS LAST, created_at DESC, id DESC"


def previous_scan_query(
    placeholder: str, *, target: str, owner_id: str | None, before: float, with_ai_review: bool, columns: str = "*"
) -> tuple[str, tuple[Any, ...]]:
    """The latest finished scan of target before then, by the same owner and of the same kind:
    `columns` of it, every one by default."""
    owner = f"owner_id = {placeholder}" if owner_id is not None else "owner_id IS NULL"
    kind = "provider IS NOT NULL" if with_ai_review else "provider IS NULL"
    query = (
        f"SELECT {columns} FROM scans WHERE target = {placeholder} AND status = 'done' AND created_at < {placeholder}"
        f" AND {owner} AND {kind} ORDER BY created_at DESC LIMIT 1"
    )
    return query, (target, before, *((owner_id,) if owner_id is not None else ()))


def badge_scan_query(placeholder: str) -> str:
    """The latest scan of a target its owner put on the target's badge: shared, finished, and
    without a baseline."""
    return (
        f"SELECT * FROM scans WHERE target = {placeholder} AND badge AND share_token_hash IS NOT NULL"
        " AND status = 'done' AND baseline IS NULL ORDER BY created_at DESC LIMIT 1"
    )


def monitor_queries(placeholder: str) -> dict[str, str]:
    """The health panel's and alerts' queries (app/monitoring.py), for either store."""
    p = placeholder
    return {
        "add": f"INSERT INTO monitor_events (created_at, kind, message, scan_id, count) VALUES ({p}, {p}, {p}, {p}, {p})",
        "counts": f"SELECT kind, SUM(count) AS total FROM monitor_events WHERE created_at >= {p} GROUP BY kind",
        "outcomes": (
            f"SELECT (SELECT COUNT(*) FROM scans WHERE created_at >= {p}) AS started,"
            f" (SELECT COUNT(*) FROM scans WHERE finished_at >= {p} AND status IN ('done', 'error')) AS finished,"
            f" (SELECT COUNT(*) FROM scans WHERE finished_at >= {p} AND status = 'error') AS failed"
        ),
        "prune": f"DELETE FROM monitor_events WHERE created_at < {p}",
    }


def last_monitor_event_query(placeholder: str, kinds: tuple[str, ...], message: str | None) -> tuple[str, tuple[Any, ...]]:
    """The latest event of these kinds; with a message, only one with that message (an alert's rule)."""
    marks = ", ".join(placeholder for _ in kinds)
    where = f"kind IN ({marks})" + (f" AND message = {placeholder}" if message is not None else "")
    params = (*kinds, *((message,) if message is not None else ()))
    return f"SELECT * FROM monitor_events WHERE {where} ORDER BY created_at DESC, id DESC LIMIT 1", params


def list_monitor_events_query(placeholder: str, kinds: tuple[str, ...]) -> tuple[str, str]:
    """A page of events, newest first, of these kinds or every one; and their count."""
    where = f"WHERE kind IN ({', '.join(placeholder for _ in kinds)})" if kinds else ""
    return (
        f"SELECT * FROM monitor_events {where} ORDER BY created_at DESC, id DESC LIMIT {placeholder} OFFSET {placeholder}",
        f"SELECT COUNT(*) AS total FROM monitor_events {where}",
    )


INSERT_SCAN_COLUMNS = (
    "id, target, status, created_at, provider, owner_id, llm_model, baseline, use_shipped_baseline, transitive_depth, upload, private_source"
)


# The next report number of an owner, '' for the server's own sequence (scans without an owner):
# each owner numbers their reports from 1, so a number tells nothing of anyone else's.
NEXT_REPORT_NO = (
    "INSERT INTO report_counters (owner, last_no) VALUES ({p}, 1)"
    " ON CONFLICT (owner) DO UPDATE SET last_no = report_counters.last_no + 1 RETURNING last_no"
)


def insert_scan_query(placeholder: str, *, max_active: int | None) -> str:
    """The scan's INSERT; with max_active, only while its owner has fewer scans in progress, as one
    statement (SQLite; Postgres takes a lock around a count and the plain INSERT instead)."""
    values = ", ".join(placeholder for _ in INSERT_SCAN_COLUMNS.split(", "))
    if max_active is None:
        return f"INSERT INTO scans ({INSERT_SCAN_COLUMNS}) VALUES ({values})"
    return (
        f"INSERT INTO scans ({INSERT_SCAN_COLUMNS}) SELECT {values}"
        f" WHERE (SELECT COUNT(*) FROM scans WHERE owner_id = {placeholder} AND status IN ('pending', 'running')) < {placeholder}"
    )


class ScanStore(Protocol):
    """Where scans and app settings live. SQLite by default; Postgres when a database URL is set."""

    def close(self) -> None: ...

    def insert_scan(
        self,
        *,
        id: str,
        target: str,
        status: str,
        created_at: float,
        provider: str | None,
        owner_id: str | None = None,
        llm_model: str | None = None,
        baseline: str | None = None,
        use_shipped_baseline: bool = False,
        transitive_depth: int | None = None,
        upload: str | None = None,
        private_source: bool = False,
        # With an owner: insert only while they have fewer pending or running scans than this,
        # checked and inserted as one step. None when they didn't have room.
        max_active: int | None = None,
    ) -> int | None:
        """Record the scan, with its owner's next report number, which it returns."""

    def update_scan(
        self,
        *,
        id: str,
        status: str,
        finished_at: float | None,
        result: dict[str, Any] | None,
        error: str | None,
    ) -> None: ...

    def start_attempt(self, scan_id: str) -> int: ...

    def unfinished_scans(self) -> list[ScanRow]: ...

    def fail_unfinished_scans(self, *, error: str, finished_at: float) -> int: ...

    def count_active_scans(self, *, owner_id: str | None = None) -> int:
        """Scans pending or running; with owner_id, only that user's."""
        ...

    def ai_token_totals(self, *, since: float, owner_id: str | None = None) -> dict[str, int]:
        """AI tokens of scans created since then, still in history; with owner_id, only that user's.
        Keys: scans (with AI usage recorded), input_tokens, output_tokens, cached_tokens."""
        ...

    def get_scan(self, id: str) -> ScanRow | None: ...

    def delete_scan(self, id: str) -> bool: ...

    def delete_scans_older_than(self, cutoff: float) -> int: ...

    # Activity entries from before audit_cutoff, and password reset links that expired before now.
    def prune_account_records(self, *, audit_cutoff: float, now: float) -> int: ...

    def get_retention_days(self) -> float | None: ...

    def set_retention_days(self, value: float | None) -> None: ...

    def previous_scan(
        self, *, target: str, owner_id: str | None, before: float, with_ai_review: bool, columns: str = "*"
    ) -> ScanRow | None: ...

    def set_share_token(self, scan_id: str, token_hash: str | None, token_secret: str | None) -> None:
        """Share the scan under that link's hash, its encrypted copy if any; None unshares it (and
        takes it off its badge)."""

    def plain_share_tokens(self) -> list[tuple[str, str]]:
        """(scan id, link) of the links still stored as they were, before they were hashed."""

    def get_shared_scan(self, token_hash: str) -> ScanRow | None: ...

    def set_badge(self, scan_id: str, on: bool) -> None: ...

    def badge_scan(self, target: str) -> ScanRow | None: ...

    def list_scans(
        self,
        limit: int,
        offset: int,
        *,
        owner_id: str | None = None,
        target: str | None = None,
        sort: str = "created_at",
        order: str = "desc",
    ) -> tuple[list[ScanRow], int]:
        """Newest first. With owner_id, only that user's scans."""
        ...

    # Scan logs and progress, for the database log store (app/scan_logs.py).

    def append_log_lines(self, scan_id: str, lines: list[str], *, keep: int, steps: int = 0) -> None:
        """Add lines to the scan's log and `steps` to its progress, in one transaction, keeping only
        its newest `keep` lines."""

    def get_log_lines(self, scan_id: str) -> list[str]: ...

    def get_log_lines_after(self, scan_id: str, after: int) -> list[tuple[int, str]]:
        """The scan's lines stored after the one with id `after`, oldest first, with their ids."""

    def increment_progress(self, scan_id: str) -> None: ...

    def get_progress(self, scan_id: str) -> int: ...

    def clear_logs(self, scan_id: str) -> None: ...

    # Accounts and sessions (app/auth).

    def create_user(self, *, id: str, email: str, password_hash: str | None, role: str, created_at: float) -> None: ...

    def create_first_user(self, *, id: str, email: str, password_hash: str, role: str, created_at: float) -> bool: ...

    def get_user(self, id: str) -> dict[str, Any] | None: ...

    def get_user_by_email(self, email: str) -> dict[str, Any] | None: ...

    def list_users(self, *, query: str | None = None) -> list[dict[str, Any]]:
        """Users with their scan counts, oldest first; `query` filters by email."""
        ...

    def count_users(self) -> int: ...

    # Everything of the user's: their scans, sessions, tokens, keys and connections; their activity
    # entries keep only ids. The uploads their scans held, for the caller to delete; None if unknown.
    def delete_user(self, id: str) -> list[str] | None: ...

    # Connected code host accounts, their tokens encrypted by the caller (app/repo_connections.py).

    def set_repo_connection(self, *, user_id: str, provider: str, account_name: str, encrypted_token: str, now: float) -> None: ...

    def get_repo_connection(self, user_id: str, provider: str) -> dict[str, Any] | None: ...

    def list_repo_connections(self, user_id: str) -> list[dict[str, Any]]: ...

    def delete_repo_connection(self, user_id: str, provider: str) -> bool: ...

    def create_api_token(
        self, *, id: str, user_id: str, name: str, token_hash: str, prefix: str, scopes: str, created_at: float, expires_at: float | None
    ) -> None: ...

    def list_api_tokens(self, user_id: str) -> list[dict[str, Any]]: ...

    def get_api_token_user(self, token_hash: str, *, now: float) -> dict[str, Any] | None: ...

    def mark_api_token_used(self, token_id: str, at: float) -> None: ...

    def delete_api_tokens_for_user(self, user_id: str) -> int:
        """Revoke every token of the user; how many there were."""

    def delete_api_token(self, token_id: str, *, user_id: str) -> dict[str, Any] | None: ...

    def get_session_created_at(self, token_hash: str) -> float | None: ...

    def get_identity_user(self, provider: str, provider_user_id: str) -> dict[str, Any] | None:
        """The user an outside identity (GitHub's numeric user ID) signs in as."""

    def list_identities(self, user_id: str) -> list[dict[str, Any]]: ...

    def add_identity(self, *, provider: str, provider_user_id: str, user_id: str, display_name: str | None, created_at: float) -> bool:
        """Link the identity to the user; False when it's linked already, to anyone."""

    def rename_identity(self, provider: str, provider_user_id: str, display_name: str | None) -> None: ...

    def delete_identity(self, user_id: str, provider: str) -> bool: ...

    def create_session(self, *, token_hash: str, user_id: str, created_at: float, expires_at: float) -> None: ...

    def get_session_user(self, token_hash: str, *, now: float) -> dict[str, Any] | None: ...

    def delete_session(self, token_hash: str) -> None: ...

    def delete_expired_sessions(self, now: float) -> int: ...

    def set_password_hash(self, user_id: str, password_hash: str) -> None: ...

    def delete_sessions_for_user(self, user_id: str, *, keep_token_hash: str | None = None) -> None: ...

    def create_password_reset(self, *, token_hash: str, user_id: str, created_at: float, expires_at: float) -> None: ...

    def consume_password_reset(self, token_hash: str, *, now: float) -> str | None: ...

    def create_pending_signup(self, *, token_hash: str, email: str, password_hash: str, created_at: float, expires_at: float) -> None: ...

    def consume_pending_signup(self, token_hash: str, *, now: float) -> dict[str, Any] | None: ...

    # Backoffice.

    def update_user(self, user_id: str, *, role: str | None = None, status: str | None = None) -> None: ...

    def set_user_quotas(self, user_id: str, *, daily_scan_quota: int | None, concurrent_scan_quota: int | None) -> None: ...

    def record_login(self, user_id: str, at: float) -> None: ...

    def count_active_admins(self) -> int: ...

    def get_allow_signup(self) -> bool | None:
        """The admin's sign-up setting, or None when it was never changed."""
        ...

    def set_allow_signup(self, value: bool | None) -> None: ...

    def get_scan_limits(self) -> dict[str, Any]:
        """The admin's scan settings: `scans_paused`, `daily_scan_quota` and `concurrent_scan_quota`,
        each None when never changed. A quota of 0 means no limit."""
        ...

    def set_scan_limits(
        self, *, scans_paused: bool | None, daily_scan_quota: int | None, concurrent_scan_quota: int | None
    ) -> None: ...

    def add_audit(
        self,
        *,
        created_at: float,
        actor_id: str | None,
        actor_email: str | None,
        action: str,
        target_id: str | None,
        target_email: str | None,
        detail: str | None,
    ) -> None: ...

    def list_audit(self, limit: int, offset: int, *, target_id: str | None = None) -> tuple[list[dict[str, Any]], int]: ...

    def overview_stats(self, *, since: float) -> dict[str, Any]: ...

    # Monitoring (app/monitoring.py).

    def add_monitor_event(self, *, created_at: float, kind: str, message: str | None, scan_id: str | None, count: int) -> None: ...

    def monitor_counts(self, *, since: float) -> dict[str, int]: ...

    def scan_outcomes(self, *, since: float) -> dict[str, int]: ...

    def last_monitor_event(self, kinds: tuple[str, ...], message: str | None = None) -> dict[str, Any] | None: ...

    def delete_monitor_events_older_than(self, cutoff: float) -> int: ...

    def list_monitor_events(self, limit: int, offset: int, kinds: tuple[str, ...]) -> tuple[list[dict[str, Any]], int]: ...

    # Stored AI provider keys and per-scan one-off keys, both encrypted by the caller.

    def set_llm_credential(
        self, *, user_id: str, provider: str, encrypted_key: str, key_hint: str, now: float
    ) -> None: ...

    def get_llm_credential(self, user_id: str) -> dict[str, Any] | None: ...

    def delete_llm_credential(self, user_id: str) -> bool: ...

    def put_scan_secret(self, *, scan_id: str, encrypted_key: str, now: float) -> None: ...

    def get_scan_secret(self, scan_id: str) -> str | None: ...

    def delete_scan_secret(self, scan_id: str) -> None: ...



def summary_columns(result: dict[str, Any] | None) -> tuple[Any, ...]:
    """The summary columns denormalised from a report, so history and usage don't need to load it."""
    risk = (result or {}).get("risk_assessment") or {}
    return risk.get("score"), risk.get("severity"), risk.get("recommendation"), ai_review_status(result), *token_totals(result)

    def count_rate_limit_hits(self, key: str, *, window_seconds: float, now: float) -> int:
        """Hits recorded for key within the window."""

    def rate_limit_hit(self, key: str, *, limit: int, window_seconds: float, now: float) -> float | None:
        """Record a hit for key if fewer than `limit` fell within the window; None when recorded,
        otherwise seconds until one frees up. Expired hits of every key are dropped on the way."""

    def rate_limit_forget(self, key: str) -> None:
        """Drop key's most recent hit: what it counted turned out not to count."""
