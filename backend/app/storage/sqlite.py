from __future__ import annotations

import functools
import json
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.storage.base import (
    NEXT_REPORT_NO,
    SUMMARY_COLUMNS,
    ScanRow,
    badge_scan_query,
    insert_scan_query,
    last_monitor_event_query,
    list_monitor_events_query,
    monitor_queries,
    previous_scan_query,
    scan_filter,
    scan_order,
    summary_columns,
)

# Append-only: never edit an entry once released, add a new version instead. Version 1 uses
# IF NOT EXISTS so databases created before migrations existed adopt it unchanged.
MIGRATIONS: list[tuple[int, list[str]]] = [
    (
        1,
        [
            """
            CREATE TABLE IF NOT EXISTS scans (
                id TEXT PRIMARY KEY,
                target TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                finished_at REAL,
                result TEXT,
                error TEXT,
                provider TEXT,
                risk_score REAL,
                severity TEXT,
                recommendation TEXT
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_scans_created_at ON scans (created_at DESC)",
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                scan_retention_days REAL
            )
            """,
        ],
    ),
    (
        2,
        [
            """
            CREATE TABLE scan_log_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id TEXT NOT NULL,
                line TEXT NOT NULL
            )
            """,
            "CREATE INDEX idx_scan_log_lines_scan ON scan_log_lines (scan_id, id)",
            "ALTER TABLE scans ADD COLUMN completed_steps INTEGER NOT NULL DEFAULT 0",
        ],
    ),
    (
        3,
        [
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """,
            """
            CREATE TABLE sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )
            """,
            "CREATE INDEX idx_sessions_user ON sessions (user_id)",
            "ALTER TABLE scans ADD COLUMN owner_id TEXT",
            "CREATE INDEX idx_scans_owner ON scans (owner_id, created_at DESC)",
        ],
    ),
    (
        4,
        [
            """
            CREATE TABLE password_resets (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                used_at REAL
            )
            """,
            "CREATE INDEX idx_password_resets_user ON password_resets (user_id)",
        ],
    ),
    (
        5,
        [
            "ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'",
            "ALTER TABLE users ADD COLUMN last_login_at REAL",
            "ALTER TABLE app_settings ADD COLUMN allow_signup INTEGER",
            """
            CREATE TABLE audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                actor_id TEXT,
                actor_email TEXT,
                action TEXT NOT NULL,
                target_id TEXT,
                target_email TEXT,
                detail TEXT
            )
            """,
            "CREATE INDEX idx_audit_log_created ON audit_log (created_at DESC)",
        ],
    ),
    (
        6,
        [
            """
            CREATE TABLE llm_credentials (
                user_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                encrypted_key TEXT NOT NULL,
                key_hint TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """,
            """
            CREATE TABLE scan_secrets (
                scan_id TEXT PRIMARY KEY,
                encrypted_key TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """,
            "ALTER TABLE scans ADD COLUMN llm_model TEXT",
        ],
    ),
    (
        7,
        [
            """
            CREATE TABLE rate_limit_hits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                hit_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )
            """,
            "CREATE INDEX idx_rate_limit_hits_key ON rate_limit_hits (key, hit_at DESC)",
            "CREATE INDEX idx_rate_limit_hits_expires ON rate_limit_hits (expires_at)",
        ],
    ),
    (
        8,
        [
            # Scan quotas and the pause switch (app/quotas.py). A NULL quota follows the server's
            # configured default; 0 means no limit.
            "ALTER TABLE app_settings ADD COLUMN scans_paused INTEGER",
            "ALTER TABLE app_settings ADD COLUMN daily_scan_quota INTEGER",
            "ALTER TABLE app_settings ADD COLUMN concurrent_scan_quota INTEGER",
        ],
    ),
    (
        9,
        [
            # Whether the scan's AI review ran: complete, degraded or failed (app/ai_review.py).
            # NULL for static scans, and for scans finished before this column existed.
            "ALTER TABLE scans ADD COLUMN ai_review TEXT",
        ],
    ),
    (
        10,
        [
            # Tokens the scan's AI review used, as the provider reported them (app/ai_usage.py).
            # NULL for static scans, for counters a provider didn't report, and for scans
            # finished before these columns existed.
            "ALTER TABLE scans ADD COLUMN ai_input_tokens INTEGER",
            "ALTER TABLE scans ADD COLUMN ai_output_tokens INTEGER",
            "ALTER TABLE scans ADD COLUMN ai_cached_tokens INTEGER",
        ],
    ),
    (
        11,
        [
            # The baseline file a scan was started with (YAML or JSON text), so a queued scan can
            # apply it wherever it runs. NULL for scans without one.
            "ALTER TABLE scans ADD COLUMN baseline TEXT",
        ],
    ),
    (
        12,
        [
            # How many levels of a skill's external references the scan follows (skillspector's
            # --transitive-depth). NULL when it follows none.
            "ALTER TABLE scans ADD COLUMN transitive_depth INTEGER",
        ],
    ),
    (
        13,
        [
            # Where a scan's uploaded file is held until it ends (app/uploads.py). NULL for scans of
            # a link.
            "ALTER TABLE scans ADD COLUMN upload TEXT",
        ],
    ),
    (
        14,
        [
            # A target's scans, newest first: the history of one target, and the scan a rescan is
            # compared with (app/rescan.py).
            "CREATE INDEX IF NOT EXISTS scans_target_created_at ON scans (target, created_at)",
        ],
    ),
    (
        15,
        [
            # The read-only link a scan's owner shared its result with (app/api/routes/shared.py),
            # until they revoke it. NULL when it isn't shared.
            "ALTER TABLE scans ADD COLUMN share_token TEXT",
            "CREATE UNIQUE INDEX IF NOT EXISTS scans_share_token ON scans (share_token)",
        ],
    ),
    (
        16,
        [
            # The history's sorts (GET /scan?sort=…): everyone's scans for admins, one user's for
            # the others. Targets already have one (scans_target_created_at).
            "CREATE INDEX IF NOT EXISTS scans_created_at ON scans (created_at)",
            "CREATE INDEX IF NOT EXISTS scans_risk_score ON scans (risk_score)",
            "CREATE INDEX IF NOT EXISTS scans_status ON scans (status)",
            "CREATE INDEX IF NOT EXISTS scans_owner_created_at ON scans (owner_id, created_at)",
            "CREATE INDEX IF NOT EXISTS scans_owner_risk_score ON scans (owner_id, risk_score)",
        ],
    ),
    (
        17,
        [
            # Personal API tokens (app/auth/api_tokens.py): like sessions, only a token's hash is
            # stored. prefix is its first characters, to tell a user's tokens apart.
            """
            CREATE TABLE api_tokens (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                prefix TEXT NOT NULL,
                scopes TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL,
                last_used_at REAL
            )
            """,
            "CREATE INDEX idx_api_tokens_user ON api_tokens (user_id)",
        ],
    ),
    (
        18,
        [
            # Whether a shared scan's owner put it on its target's status badge
            # (app/api/routes/badge.py). Only a shared scan can be; revoking the link takes it off.
            "ALTER TABLE scans ADD COLUMN badge INTEGER NOT NULL DEFAULT 0",
        ],
    ),
    (
        19,
        [
            # What the health panel and alerts read (app/monitoring.py): failed scans, sign-in
            # lockouts, and the alerts sent. Kept 30 days.
            """
            CREATE TABLE monitor_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                kind TEXT NOT NULL,
                message TEXT,
                scan_id TEXT,
                count INTEGER NOT NULL DEFAULT 1
            )
            """,
            "CREATE INDEX idx_monitor_events_kind ON monitor_events (kind, created_at)",
            # Scans that finished within a window: the failure rate.
            "CREATE INDEX IF NOT EXISTS scans_finished_at ON scans (finished_at)",
        ],
    ),
    (
        20,
        [
            # A user's own scan quotas (app/quotas.py), set from the backoffice: NULL follows the
            # server's, 0 is no limit.
            "ALTER TABLE users ADD COLUMN daily_scan_quota INTEGER",
            "ALTER TABLE users ADD COLUMN concurrent_scan_quota INTEGER",
        ],
    ),
    (
        21,
        [
            # How many times a scan was started (app/scanner.py's run_job): a self-hosted API picks
            # unfinished scans back up when it restarts, up to a limit (app/jobs/in_process.py).
            "ALTER TABLE scans ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0",
        ],
    ),
    (
        22,
        [
            # A user's connected code host accounts (app/repo_connections.py), to scan their private
            # repositories: one per provider, its tokens encrypted with SECRET_KEY.
            """
            CREATE TABLE repo_connections (
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                account_name TEXT NOT NULL,
                encrypted_token TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (user_id, provider)
            )
            """,
            # The scan reads a private repository, with its owner's connection: its result stays
            # theirs (no share link or badge unless they confirm, and only they open it).
            "ALTER TABLE scans ADD COLUMN private_source INTEGER NOT NULL DEFAULT 0",
        ],
    ),
    (
        23,
        [
            # Apply the baseline the scanned skill ships, if any (app/scan_runner.py's
            # shipped_baseline): the user opted in.
            "ALTER TABLE scans ADD COLUMN use_shipped_baseline INTEGER NOT NULL DEFAULT 0",
        ],
    ),
    (
        24,
        [
            # A sign-up waiting for its email to be confirmed (app/auth's start_signup), so the
            # answer to signing up doesn't tell whether the address already has an account.
            """
            CREATE TABLE pending_signups (
                token_hash TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )
            """,
            "CREATE INDEX idx_pending_signups_email ON pending_signups (email)",
        ],
    ),
    (
        25,
        [
            # Each covered by another index, read either way: scans_created_at, and
            # scans_owner_created_at. Every insert and update paid for both.
            "DROP INDEX IF EXISTS idx_scans_created_at",
            "DROP INDEX IF EXISTS idx_scans_owner",
            # A user's activity in the backoffice (list_audit), newest first.
            "CREATE INDEX idx_audit_log_target ON audit_log (target_id, id)",
            # A user's scans in progress, counted each time they start one (the quota).
            "CREATE INDEX idx_scans_owner_status ON scans (owner_id, status)",
        ],
    ),
    (
        26,
        [
            # Share links, stored as their hash (app/sharing.py): a copy of the database opens no shared
            # result. With SECRET_KEY, the link also kept encrypted, for its owner to copy again.
            # share_token, the plain link before, is emptied at startup.
            "ALTER TABLE scans ADD COLUMN share_token_hash TEXT",
            "CREATE UNIQUE INDEX IF NOT EXISTS scans_share_token_hash ON scans (share_token_hash)",
            "ALTER TABLE scans ADD COLUMN share_token_secret TEXT",
        ],
    ),
    (
        27,
        [
            # Accounts made with GitHub have no password: users.password_hash may be NULL. SQLite
            # can't drop a NOT NULL in place, so the table is rebuilt, with every row and column.
            """
            CREATE TABLE users_rebuilt (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT,
                role TEXT NOT NULL,
                created_at REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                last_login_at REAL,
                daily_scan_quota INTEGER,
                concurrent_scan_quota INTEGER
            )
            """,
            (
                "INSERT INTO users_rebuilt (id, email, password_hash, role, created_at, status, last_login_at, daily_scan_quota, concurrent_scan_quota)"
                " SELECT id, email, password_hash, role, created_at, status, last_login_at, daily_scan_quota, concurrent_scan_quota FROM users"
            ),
            "DROP TABLE users",
            "ALTER TABLE users_rebuilt RENAME TO users",
            # Ways to sign in other than a password (app/auth/github_sign_in.py): GitHub, by its
            # numeric user ID, which a rename doesn't change. display_name is only for the Account page.
            """
            CREATE TABLE user_identities (
                provider TEXT NOT NULL,
                provider_user_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                display_name TEXT,
                created_at REAL NOT NULL,
                PRIMARY KEY (provider, provider_user_id)
            )
            """,
            "CREATE INDEX idx_user_identities_user ON user_identities (user_id)",
        ],
    ),
    (
        28,
        [
            # Each scan's report number among its owner's (app/storage/base.py's NEXT_REPORT_NO): its
            # owner's own sequence, or the server's ('') for scans without one. A label only: links
            # and the API keep the id.
            "CREATE TABLE report_counters (owner TEXT PRIMARY KEY, last_no INTEGER NOT NULL)",
            "ALTER TABLE scans ADD COLUMN report_no INTEGER",
            (
                "UPDATE scans SET report_no = (SELECT numbered.n FROM (SELECT id, ROW_NUMBER() OVER"
                " (PARTITION BY COALESCE(owner_id, '') ORDER BY created_at, id) AS n FROM scans) AS numbered"
                " WHERE numbered.id = scans.id)"
            ),
            "INSERT INTO report_counters (owner, last_no) SELECT COALESCE(owner_id, ''), MAX(report_no) FROM scans GROUP BY COALESCE(owner_id, '')",
        ],
    ),
]

def _locked[T](method: Callable[..., T]) -> Callable[..., T]:
    """Serialise access: the one connection is shared with skillspector's worker threads, which
    write log lines while a scan runs."""

    @functools.wraps(method)
    def wrapper(self: SQLiteStore, *args: Any, **kwargs: Any) -> T:
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


def _to_row(row: sqlite3.Row) -> ScanRow:
    scan = dict(row)
    if scan.get("result") is not None:
        scan["result"] = json.loads(scan["result"])
    return scan


class SQLiteStore:
    def __init__(self, path: str, *, default_retention_days: float | None) -> None:
        db_path = Path(path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        # Safe with WAL (a power cut can lose the last commits, never corrupt the database), and makes
        # each commit cheaper: no sync on every one.
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._migrate()
        self._conn.execute(
            "INSERT OR IGNORE INTO app_settings (id, scan_retention_days) VALUES (1, ?)",
            (default_retention_days,),
        )
        self._conn.commit()

    def _migrate(self) -> None:
        conn = self._conn
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at REAL NOT NULL)")
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        for version, statements in MIGRATIONS:
            if version in applied:
                continue
            with conn:
                for statement in statements:
                    conn.execute(statement)
                conn.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)", (version, time.time()))

    @_locked
    def close(self) -> None:
        self._conn.close()

    @_locked
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
        max_active: int | None = None,
    ) -> int | None:
        values = (id, target, status, created_at, provider, owner_id, llm_model, baseline, use_shipped_baseline, transitive_depth, upload, private_source)
        limited = max_active is not None and owner_id is not None
        # One statement: SQLite runs it whole, whichever connection or process sends another.
        cursor = self._conn.execute(
            insert_scan_query("?", max_active=max_active if limited else None),
            (*values, owner_id, max_active) if limited else values,
        )
        if cursor.rowcount != 1:
            self._conn.commit()
            return None
        # In the insert's transaction: numbered once it's in, and only then.
        report_no = self._conn.execute(NEXT_REPORT_NO.format(p="?"), (owner_id or "",)).fetchone()[0]
        self._conn.execute("UPDATE scans SET report_no = ? WHERE id = ?", (report_no, id))
        self._conn.commit()
        return report_no

    @_locked
    def update_scan(
        self,
        *,
        id: str,
        status: str,
        finished_at: float | None,
        result: dict[str, Any] | None,
        error: str | None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE scans
            SET status = ?, finished_at = ?, result = ?, error = ?,
                risk_score = ?, severity = ?, recommendation = ?, ai_review = ?,
                ai_input_tokens = ?, ai_output_tokens = ?, ai_cached_tokens = ?
            WHERE id = ?
            """,
            (
                status,
                finished_at,
                json.dumps(result) if result is not None else None,
                error,
                *summary_columns(result),
                id,
            ),
        )
        self._conn.commit()

    @_locked
    def start_attempt(self, scan_id: str) -> int:
        self._conn.execute("UPDATE scans SET attempts = attempts + 1 WHERE id = ?", (scan_id,))
        self._conn.commit()
        row = self._conn.execute("SELECT attempts FROM scans WHERE id = ?", (scan_id,)).fetchone()
        return int(row[0]) if row else 0

    @_locked
    def unfinished_scans(self) -> list[ScanRow]:
        rows = self._conn.execute("SELECT * FROM scans WHERE status IN ('pending', 'running') ORDER BY created_at").fetchall()
        return [_to_row(row) for row in rows]

    @_locked
    def fail_unfinished_scans(self, *, error: str, finished_at: float) -> int:
        cursor = self._conn.execute(
            "UPDATE scans SET status = 'error', error = ?, finished_at = ? WHERE status IN ('pending', 'running')",
            (error, finished_at),
        )
        self._conn.commit()
        return cursor.rowcount

    @_locked
    def count_active_scans(self, *, owner_id: str | None = None) -> int:
        where, params = (" AND owner_id = ?", (owner_id,)) if owner_id is not None else ("", ())
        query = f"SELECT COUNT(*) FROM scans WHERE status IN ('pending', 'running'){where}"
        return self._conn.execute(query, params).fetchone()[0]

    @_locked
    def ai_token_totals(self, *, since: float, owner_id: str | None = None) -> dict[str, int]:
        where, params = (" AND owner_id = ?", (owner_id,)) if owner_id is not None else ("", ())
        row = self._conn.execute(
            f"""
            SELECT COUNT(ai_input_tokens) AS scans, COALESCE(SUM(ai_input_tokens), 0) AS input_tokens,
                   COALESCE(SUM(ai_output_tokens), 0) AS output_tokens, COALESCE(SUM(ai_cached_tokens), 0) AS cached_tokens
            FROM scans WHERE created_at >= ?{where}
            """,
            (since, *params),
        ).fetchone()
        return dict(row)

    @_locked
    def get_scan(self, id: str) -> ScanRow | None:
        row = self._conn.execute("SELECT * FROM scans WHERE id = ?", (id,)).fetchone()
        return _to_row(row) if row is not None else None

    @_locked
    def previous_scan(
        self, *, target: str, owner_id: str | None, before: float, with_ai_review: bool, columns: str = "*"
    ) -> ScanRow | None:
        query, params = previous_scan_query(
            "?", target=target, owner_id=owner_id, before=before, with_ai_review=with_ai_review, columns=columns
        )
        row = self._conn.execute(query, params).fetchone()
        return _to_row(row) if row is not None else None

    @_locked
    def set_share_token(self, scan_id: str, token_hash: str | None, token_secret: str | None) -> None:
        # An unshared scan is off its badge too.
        self._conn.execute(
            "UPDATE scans SET share_token = NULL, share_token_hash = ?, share_token_secret = ?, badge = badge AND ? WHERE id = ?",
            (token_hash, token_secret, token_hash is not None, scan_id),
        )
        self._conn.commit()

    @_locked
    def plain_share_tokens(self) -> list[tuple[str, str]]:
        rows = self._conn.execute("SELECT id, share_token FROM scans WHERE share_token IS NOT NULL").fetchall()
        return [(row["id"], row["share_token"]) for row in rows]

    @_locked
    def get_shared_scan(self, token_hash: str) -> ScanRow | None:
        row = self._conn.execute("SELECT * FROM scans WHERE share_token_hash = ?", (token_hash,)).fetchone()
        return _to_row(row) if row is not None else None

    @_locked
    def set_badge(self, scan_id: str, on: bool) -> None:
        self._conn.execute("UPDATE scans SET badge = ? WHERE id = ?", (on, scan_id))
        self._conn.commit()

    @_locked
    def badge_scan(self, target: str) -> ScanRow | None:
        row = self._conn.execute(badge_scan_query("?"), (target,)).fetchone()
        return _to_row(row) if row is not None else None

    @_locked
    def delete_scan(self, id: str) -> bool:
        cursor = self._conn.execute("DELETE FROM scans WHERE id = ?", (id,))
        self._conn.execute("DELETE FROM scan_log_lines WHERE scan_id = ?", (id,))
        self._conn.execute("DELETE FROM scan_secrets WHERE scan_id = ?", (id,))
        self._conn.commit()
        return cursor.rowcount > 0

    @_locked
    def prune_account_records(self, *, audit_cutoff: float, now: float) -> int:
        deleted = self._conn.execute("DELETE FROM audit_log WHERE created_at < ?", (audit_cutoff,)).rowcount
        self._conn.execute("DELETE FROM password_resets WHERE expires_at < ?", (now,))
        self._conn.execute("DELETE FROM pending_signups WHERE expires_at < ?", (now,))
        self._conn.commit()
        return deleted

    @_locked
    def delete_scans_older_than(self, cutoff: float) -> int:
        # Pending/running scans are still owned by a live job; deleting them would lose the result.
        # Their log lines and secrets first, found by the same condition through the indexes, so the
        # sweep touches only the rows it deletes.
        expired = "SELECT id FROM scans WHERE created_at < ? AND status NOT IN ('pending', 'running')"
        self._conn.execute(f"DELETE FROM scan_log_lines WHERE scan_id IN ({expired})", (cutoff,))
        self._conn.execute(f"DELETE FROM scan_secrets WHERE scan_id IN ({expired})", (cutoff,))
        cursor = self._conn.execute("DELETE FROM scans WHERE created_at < ? AND status NOT IN ('pending', 'running')", (cutoff,))
        self._conn.commit()
        return cursor.rowcount

    @_locked
    def get_retention_days(self) -> float | None:
        row = self._conn.execute("SELECT scan_retention_days FROM app_settings WHERE id = 1").fetchone()
        return row["scan_retention_days"] if row else None

    @_locked
    def set_retention_days(self, value: float | None) -> None:
        self._conn.execute("UPDATE app_settings SET scan_retention_days = ? WHERE id = 1", (value,))
        self._conn.commit()

    @_locked
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
        where, params = scan_filter("?", owner_id=owner_id, target=target)
        rows = self._conn.execute(
            f"SELECT {SUMMARY_COLUMNS} FROM scans {where} {scan_order(sort, order)} LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        total = self._conn.execute(f"SELECT COUNT(*) FROM scans {where}", params).fetchone()[0]
        return [dict(row) for row in rows], total

    @_locked
    def append_log_lines(self, scan_id: str, lines: list[str], *, keep: int, steps: int = 0) -> None:
        if steps:
            self._conn.execute("UPDATE scans SET completed_steps = completed_steps + ? WHERE id = ?", (steps, scan_id))
        if not lines:
            self._conn.commit()
            return
        self._conn.executemany("INSERT INTO scan_log_lines (scan_id, line) VALUES (?, ?)", [(scan_id, line) for line in lines])
        # Keep only the newest `keep` lines of this scan.
        self._conn.execute(
            """
            DELETE FROM scan_log_lines
            WHERE scan_id = ? AND id <= (
                SELECT id FROM scan_log_lines WHERE scan_id = ? ORDER BY id DESC LIMIT 1 OFFSET ?
            )
            """,
            (scan_id, scan_id, keep),
        )
        self._conn.commit()

    @_locked
    def get_log_lines(self, scan_id: str) -> list[str]:
        rows = self._conn.execute("SELECT line FROM scan_log_lines WHERE scan_id = ? ORDER BY id", (scan_id,))
        return [row["line"] for row in rows]

    @_locked
    def get_log_lines_after(self, scan_id: str, after: int) -> list[tuple[int, str]]:
        rows = self._conn.execute(
            "SELECT id, line FROM scan_log_lines WHERE scan_id = ? AND id > ? ORDER BY id", (scan_id, after)
        )
        return [(row["id"], row["line"]) for row in rows]

    @_locked
    def increment_progress(self, scan_id: str) -> None:
        self._conn.execute("UPDATE scans SET completed_steps = completed_steps + 1 WHERE id = ?", (scan_id,))
        self._conn.commit()

    @_locked
    def get_progress(self, scan_id: str) -> int:
        row = self._conn.execute("SELECT completed_steps FROM scans WHERE id = ?", (scan_id,)).fetchone()
        return row["completed_steps"] if row else 0

    @_locked
    def clear_logs(self, scan_id: str) -> None:
        self._conn.execute("DELETE FROM scan_log_lines WHERE scan_id = ?", (scan_id,))
        self._conn.execute("UPDATE scans SET completed_steps = 0 WHERE id = ?", (scan_id,))
        self._conn.commit()

    # Accounts (app/auth). Emails are stored lower-cased by the caller.

    @_locked
    def create_user(self, *, id: str, email: str, password_hash: str | None, role: str, created_at: float) -> None:
        self._conn.execute(
            "INSERT INTO users (id, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (id, email, password_hash, role, created_at),
        )
        self._conn.commit()

    @_locked
    def create_first_user(self, *, id: str, email: str, password_hash: str, role: str, created_at: float) -> bool:
        """Create the account only if none exists yet; False when another request got there first."""
        cursor = self._conn.execute(
            """
            INSERT INTO users (id, email, password_hash, role, created_at)
            SELECT ?, ?, ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM users)
            """,
            (id, email, password_hash, role, created_at),
        )
        self._conn.commit()
        return cursor.rowcount == 1

    @_locked
    def get_user(self, id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM users WHERE id = ?", (id,)).fetchone()
        return dict(row) if row else None

    @_locked
    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None

    @_locked
    def list_users(self, *, query: str | None = None) -> list[dict[str, Any]]:
        where, params = ("WHERE users.email LIKE ?", (f"%{query.lower()}%",)) if query else ("", ())
        rows = self._conn.execute(f"""
            SELECT users.id, users.email, users.role, users.status, users.created_at, users.last_login_at,
                   users.daily_scan_quota, users.concurrent_scan_quota, COALESCE(counts.scans, 0) AS scan_count
            FROM users
            LEFT JOIN (SELECT owner_id, COUNT(*) AS scans FROM scans GROUP BY owner_id) AS counts
                ON counts.owner_id = users.id
            {where}
            ORDER BY users.created_at
""", params)
        return [dict(row) for row in rows]

    @_locked
    def count_users(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    @_locked
    def delete_user(self, id: str) -> list[str] | None:
        if self._conn.execute("SELECT 1 FROM users WHERE id = ?", (id,)).fetchone() is None:
            return None
        uploads = [row["upload"] for row in self._conn.execute("SELECT upload FROM scans WHERE owner_id = ? AND upload IS NOT NULL", (id,))]
        self._conn.execute("DELETE FROM scan_log_lines WHERE scan_id IN (SELECT id FROM scans WHERE owner_id = ?)", (id,))
        self._conn.execute("DELETE FROM scan_secrets WHERE scan_id IN (SELECT id FROM scans WHERE owner_id = ?)", (id,))
        self._conn.execute("DELETE FROM scans WHERE owner_id = ?", (id,))
        # Fixed names, never input.
        for table in ("sessions", "password_resets", "llm_credentials", "api_tokens", "repo_connections", "user_identities"):
            self._conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (id,))
        self._conn.execute("UPDATE audit_log SET actor_email = NULL, detail = NULL WHERE actor_id = ?", (id,))
        self._conn.execute("UPDATE audit_log SET target_email = NULL, detail = NULL WHERE target_id = ?", (id,))
        self._conn.execute("DELETE FROM report_counters WHERE owner = ?", (id,))
        self._conn.execute("DELETE FROM users WHERE id = ?", (id,))
        self._conn.commit()
        return uploads

    @_locked
    def set_repo_connection(self, *, user_id: str, provider: str, account_name: str, encrypted_token: str, now: float) -> None:
        self._conn.execute(
            """
            INSERT INTO repo_connections (user_id, provider, account_name, encrypted_token, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, provider) DO UPDATE SET
                account_name = excluded.account_name, encrypted_token = excluded.encrypted_token, updated_at = excluded.updated_at
            """,
            (user_id, provider, account_name, encrypted_token, now, now),
        )
        self._conn.commit()

    @_locked
    def get_repo_connection(self, user_id: str, provider: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM repo_connections WHERE user_id = ? AND provider = ?", (user_id, provider)).fetchone()
        return dict(row) if row else None

    @_locked
    def list_repo_connections(self, user_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM repo_connections WHERE user_id = ? ORDER BY provider", (user_id,)).fetchall()
        return [dict(row) for row in rows]

    @_locked
    def delete_repo_connection(self, user_id: str, provider: str) -> bool:
        cursor = self._conn.execute("DELETE FROM repo_connections WHERE user_id = ? AND provider = ?", (user_id, provider))
        self._conn.commit()
        return cursor.rowcount > 0

    @_locked
    def create_api_token(self, *, id: str, user_id: str, name: str, token_hash: str, prefix: str, scopes: str, created_at: float, expires_at: float | None) -> None:
        self._conn.execute(
            "INSERT INTO api_tokens (id, user_id, name, token_hash, prefix, scopes, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (id, user_id, name, token_hash, prefix, scopes, created_at, expires_at),
        )
        self._conn.commit()

    @_locked
    def list_api_tokens(self, user_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, user_id, name, prefix, scopes, created_at, expires_at, last_used_at FROM api_tokens WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    @_locked
    def get_api_token_user(self, token_hash: str, *, now: float) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT users.id, users.email, users.role, users.status, users.created_at, users.last_login_at,
                   users.daily_scan_quota, users.concurrent_scan_quota,
                   api_tokens.id AS token_id, api_tokens.name AS token_name, api_tokens.scopes AS token_scopes,
                   api_tokens.last_used_at AS token_last_used_at
            FROM api_tokens JOIN users ON users.id = api_tokens.user_id
            WHERE api_tokens.token_hash = ? AND (api_tokens.expires_at IS NULL OR api_tokens.expires_at > ?)
              AND users.status = 'active'
            """,
            (token_hash, now),
        ).fetchone()
        return dict(row) if row else None

    @_locked
    def mark_api_token_used(self, token_id: str, at: float) -> None:
        self._conn.execute("UPDATE api_tokens SET last_used_at = ? WHERE id = ?", (at, token_id))
        self._conn.commit()

    @_locked
    def delete_api_tokens_for_user(self, user_id: str) -> int:
        deleted = self._conn.execute("DELETE FROM api_tokens WHERE user_id = ?", (user_id,)).rowcount
        self._conn.commit()
        return deleted

    @_locked
    def delete_api_token(self, token_id: str, *, user_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT id, user_id, name, prefix, scopes, created_at, expires_at, last_used_at FROM api_tokens WHERE id = ? AND user_id = ?", (token_id, user_id)
        ).fetchone()
        if row is None:
            return None
        self._conn.execute("DELETE FROM api_tokens WHERE id = ?", (token_id,))
        self._conn.commit()
        return dict(row)

    @_locked
    def create_session(self, *, token_hash: str, user_id: str, created_at: float, expires_at: float) -> None:
        self._conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token_hash, user_id, created_at, expires_at),
        )
        self._conn.commit()

    @_locked
    def get_session_user(self, token_hash: str, *, now: float) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT users.id, users.email, users.role, users.status, users.created_at, users.last_login_at,
                   users.daily_scan_quota, users.concurrent_scan_quota
            FROM sessions JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ? AND sessions.expires_at > ? AND users.status = 'active'
            """,
            (token_hash, now),
        ).fetchone()
        return dict(row) if row else None

    @_locked
    def delete_session(self, token_hash: str) -> None:
        self._conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
        self._conn.commit()

    @_locked
    def get_session_created_at(self, token_hash: str) -> float | None:
        row = self._conn.execute("SELECT created_at FROM sessions WHERE token_hash = ?", (token_hash,)).fetchone()
        return row["created_at"] if row else None

    @_locked
    def get_identity_user(self, provider: str, provider_user_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT users.* FROM user_identities JOIN users ON users.id = user_identities.user_id"
            " WHERE user_identities.provider = ? AND user_identities.provider_user_id = ?",
            (provider, provider_user_id),
        ).fetchone()
        return dict(row) if row else None

    @_locked
    def list_identities(self, user_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT provider, display_name, created_at FROM user_identities WHERE user_id = ? ORDER BY provider", (user_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    @_locked
    def add_identity(self, *, provider: str, provider_user_id: str, user_id: str, display_name: str | None, created_at: float) -> bool:
        cursor = self._conn.execute(
            "INSERT OR IGNORE INTO user_identities (provider, provider_user_id, user_id, display_name, created_at) VALUES (?, ?, ?, ?, ?)",
            (provider, provider_user_id, user_id, display_name, created_at),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    @_locked
    def rename_identity(self, provider: str, provider_user_id: str, display_name: str | None) -> None:
        self._conn.execute(
            "UPDATE user_identities SET display_name = ? WHERE provider = ? AND provider_user_id = ?", (display_name, provider, provider_user_id)
        )
        self._conn.commit()

    @_locked
    def delete_identity(self, user_id: str, provider: str) -> bool:
        cursor = self._conn.execute("DELETE FROM user_identities WHERE user_id = ? AND provider = ?", (user_id, provider))
        self._conn.commit()
        return cursor.rowcount > 0

    @_locked
    def delete_expired_sessions(self, now: float) -> int:
        cursor = self._conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        self._conn.commit()
        return cursor.rowcount

    @_locked
    def set_password_hash(self, user_id: str, password_hash: str) -> None:
        self._conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
        self._conn.commit()

    @_locked
    def delete_sessions_for_user(self, user_id: str, *, keep_token_hash: str | None = None) -> None:
        self._conn.execute(
            "DELETE FROM sessions WHERE user_id = ? AND token_hash IS NOT ?", (user_id, keep_token_hash)
        )
        self._conn.commit()

    @_locked
    def create_password_reset(self, *, token_hash: str, user_id: str, created_at: float, expires_at: float) -> None:
        # Only the newest link works: issuing one cancels the user's earlier links.
        self._conn.execute("DELETE FROM password_resets WHERE user_id = ?", (user_id,))
        self._conn.execute(
            "INSERT INTO password_resets (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token_hash, user_id, created_at, expires_at),
        )
        self._conn.commit()

    @_locked
    def consume_password_reset(self, token_hash: str, *, now: float) -> str | None:
        """Mark an unused, unexpired reset as used and return its user id, in one statement."""
        row = self._conn.execute(
            """
            UPDATE password_resets SET used_at = ?
            WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?
            RETURNING user_id
            """,
            (now, token_hash, now),
        ).fetchone()
        self._conn.commit()
        return row["user_id"] if row else None

    @_locked
    def create_pending_signup(self, *, token_hash: str, email: str, password_hash: str, created_at: float, expires_at: float) -> None:
        # Only the newest link works: signing up again cancels the address's earlier links.
        self._conn.execute("DELETE FROM pending_signups WHERE email = ?", (email,))
        self._conn.execute(
            "INSERT INTO pending_signups (token_hash, email, password_hash, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (token_hash, email, password_hash, created_at, expires_at),
        )
        self._conn.commit()

    @_locked
    def consume_pending_signup(self, token_hash: str, *, now: float) -> dict[str, Any] | None:
        """Remove an unexpired pending sign-up and return its email and password hash, in one statement."""
        row = self._conn.execute(
            "DELETE FROM pending_signups WHERE token_hash = ? AND expires_at > ? RETURNING email, password_hash",
            (token_hash, now),
        ).fetchone()
        self._conn.commit()
        return dict(row) if row else None

    @_locked
    def update_user(self, user_id: str, *, role: str | None = None, status: str | None = None) -> None:
        self._conn.execute(
            "UPDATE users SET role = COALESCE(?, role), status = COALESCE(?, status) WHERE id = ?",
            (role, status, user_id),
        )
        self._conn.commit()

    @_locked
    def set_user_quotas(self, user_id: str, *, daily_scan_quota: int | None, concurrent_scan_quota: int | None) -> None:
        self._conn.execute(
            "UPDATE users SET daily_scan_quota = ?, concurrent_scan_quota = ? WHERE id = ?",
            (daily_scan_quota, concurrent_scan_quota, user_id),
        )
        self._conn.commit()

    @_locked
    def record_login(self, user_id: str, at: float) -> None:
        self._conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (at, user_id))
        self._conn.commit()

    @_locked
    def count_active_admins(self) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'admin' AND status = 'active'"
        ).fetchone()[0]

    @_locked
    def get_allow_signup(self) -> bool | None:
        row = self._conn.execute("SELECT allow_signup FROM app_settings WHERE id = 1").fetchone()
        return None if row is None or row["allow_signup"] is None else bool(row["allow_signup"])

    @_locked
    def get_scan_limits(self) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT scans_paused, daily_scan_quota, concurrent_scan_quota FROM app_settings WHERE id = 1"
        ).fetchone()
        if row is None:
            return {"scans_paused": None, "daily_scan_quota": None, "concurrent_scan_quota": None}
        paused = row["scans_paused"]
        return {
            "scans_paused": None if paused is None else bool(paused),
            "daily_scan_quota": row["daily_scan_quota"],
            "concurrent_scan_quota": row["concurrent_scan_quota"],
        }

    @_locked
    def set_scan_limits(
        self, *, scans_paused: bool | None, daily_scan_quota: int | None, concurrent_scan_quota: int | None
    ) -> None:
        self._conn.execute(
            "UPDATE app_settings SET scans_paused = ?, daily_scan_quota = ?, concurrent_scan_quota = ? WHERE id = 1",
            (None if scans_paused is None else int(scans_paused), daily_scan_quota, concurrent_scan_quota),
        )
        self._conn.commit()

    @_locked
    def set_allow_signup(self, value: bool | None) -> None:
        self._conn.execute(
            "UPDATE app_settings SET allow_signup = ? WHERE id = 1", (None if value is None else int(value),)
        )
        self._conn.commit()

    @_locked
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
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO audit_log (created_at, actor_id, actor_email, action, target_id, target_email, detail)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (created_at, actor_id, actor_email, action, target_id, target_email, detail),
        )
        self._conn.commit()

    @_locked
    def add_monitor_event(self, *, created_at: float, kind: str, message: str | None, scan_id: str | None, count: int) -> None:
        self._conn.execute(monitor_queries("?")["add"], (created_at, kind, message, scan_id, count))
        self._conn.commit()

    @_locked
    def monitor_counts(self, *, since: float) -> dict[str, int]:
        rows = self._conn.execute(monitor_queries("?")["counts"], (since,)).fetchall()
        return {row["kind"]: int(row["total"]) for row in rows}

    @_locked
    def scan_outcomes(self, *, since: float) -> dict[str, int]:
        row = self._conn.execute(monitor_queries("?")["outcomes"], (since, since, since)).fetchone()
        return {key: int(row[key]) for key in ("started", "finished", "failed")}

    @_locked
    def last_monitor_event(self, kinds: tuple[str, ...], message: str | None = None) -> dict[str, Any] | None:
        row = self._conn.execute(*last_monitor_event_query("?", kinds, message)).fetchone()
        return dict(row) if row is not None else None

    @_locked
    def delete_monitor_events_older_than(self, cutoff: float) -> int:
        cursor = self._conn.execute(monitor_queries("?")["prune"], (cutoff,))
        self._conn.commit()
        return cursor.rowcount

    @_locked
    def list_monitor_events(self, limit: int, offset: int, kinds: tuple[str, ...]) -> tuple[list[dict[str, Any]], int]:
        rows_query, count_query = list_monitor_events_query("?", kinds)
        rows = self._conn.execute(rows_query, (*kinds, limit, offset)).fetchall()
        total = self._conn.execute(count_query, kinds).fetchone()["total"]
        return [dict(row) for row in rows], int(total)

    @_locked
    def list_audit(self, limit: int, offset: int, *, target_id: str | None = None) -> tuple[list[dict[str, Any]], int]:
        where, params = ("WHERE target_id = ?", (target_id,)) if target_id else ("", ())
        rows = self._conn.execute(
            f"SELECT * FROM audit_log {where} ORDER BY id DESC LIMIT ? OFFSET ?", (*params, limit, offset)
        ).fetchall()
        total = self._conn.execute(f"SELECT COUNT(*) FROM audit_log {where}", params).fetchone()[0]
        return [dict(row) for row in rows], total

    @_locked
    def overview_stats(self, *, since: float) -> dict[str, Any]:
        users = self._conn.execute(
            """
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(role = 'admin'), 0) AS admins,
                   COALESCE(SUM(status = 'suspended'), 0) AS suspended,
                   COALESCE(SUM(created_at >= ?), 0) AS new
            FROM users
            """,
            (since,),
        ).fetchone()
        scans = self._conn.execute(
            """
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(created_at >= ?), 0) AS recent,
                   COALESCE(SUM(recommendation = 'DO_NOT_INSTALL'), 0) AS do_not_install,
                   COALESCE(SUM(recommendation = 'CAUTION'), 0) AS caution,
                   COALESCE(SUM(recommendation = 'SAFE'), 0) AS safe,
                   COALESCE(SUM(status = 'error'), 0) AS failed,
                   COALESCE(SUM(status IN ('pending', 'running')), 0) AS active
            FROM scans
            """,
            (since,),
        ).fetchone()
        return {"users": dict(users), "scans": dict(scans)}

    # Stored AI provider keys (encrypted by the caller; see app/secrets_box.py).

    @_locked
    def set_llm_credential(
        self, *, user_id: str, provider: str, encrypted_key: str, key_hint: str, now: float
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO llm_credentials (user_id, provider, encrypted_key, key_hint, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id) DO UPDATE SET
                provider = excluded.provider, encrypted_key = excluded.encrypted_key,
                key_hint = excluded.key_hint, updated_at = excluded.updated_at
            """,
            (user_id, provider, encrypted_key, key_hint, now, now),
        )
        self._conn.commit()

    @_locked
    def get_llm_credential(self, user_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM llm_credentials WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    @_locked
    def delete_llm_credential(self, user_id: str) -> bool:
        cursor = self._conn.execute("DELETE FROM llm_credentials WHERE user_id = ?", (user_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    @_locked
    def put_scan_secret(self, *, scan_id: str, encrypted_key: str, now: float) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO scan_secrets (scan_id, encrypted_key, created_at) VALUES (?, ?, ?)",
            (scan_id, encrypted_key, now),
        )
        self._conn.commit()

    @_locked
    def get_scan_secret(self, scan_id: str) -> str | None:
        row = self._conn.execute("SELECT encrypted_key FROM scan_secrets WHERE scan_id = ?", (scan_id,)).fetchone()
        return row["encrypted_key"] if row else None

    @_locked
    def delete_scan_secret(self, scan_id: str) -> None:
        self._conn.execute("DELETE FROM scan_secrets WHERE scan_id = ?", (scan_id,))
        self._conn.commit()

    # Rate limits (app/rate_limit.py), when INSKECT_RATE_LIMIT_STORE=database, and daily
    # scan quotas (app/quotas.py), always.

    @_locked
    def count_rate_limit_hits(self, key: str, *, window_seconds: float, now: float) -> int:
        query = "SELECT COUNT(*) FROM rate_limit_hits WHERE key = ? AND hit_at > ?"
        return self._conn.execute(query, (key, now - window_seconds)).fetchone()[0]

    @_locked
    def rate_limit_hit(self, key: str, *, limit: int, window_seconds: float, now: float) -> float | None:
        self._conn.execute("DELETE FROM rate_limit_hits WHERE expires_at <= ?", (now,))
        recent = self._conn.execute(
            "SELECT hit_at FROM rate_limit_hits WHERE key = ? AND hit_at > ? ORDER BY hit_at DESC LIMIT ?",
            (key, now - window_seconds, limit),
        ).fetchall()
        if len(recent) >= limit:
            self._conn.commit()
            return recent[-1]["hit_at"] + window_seconds - now
        self._conn.execute(
            "INSERT INTO rate_limit_hits (key, hit_at, expires_at) VALUES (?, ?, ?)",
            (key, now, now + window_seconds),
        )
        self._conn.commit()
        return None

    @_locked
    def rate_limit_forget(self, key: str) -> None:
        self._conn.execute(
            "DELETE FROM rate_limit_hits WHERE id = (SELECT id FROM rate_limit_hits WHERE key = ? ORDER BY hit_at DESC LIMIT 1)",
            (key,),
        )
        self._conn.commit()
