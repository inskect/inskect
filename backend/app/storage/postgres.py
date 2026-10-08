from __future__ import annotations

import time
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

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

# Serialises migrations when several instances start at once (any constant works, it just has to
# be the same everywhere).
_MIGRATION_LOCK_ID = 71_182_031

# Append-only: never edit an entry once released, add a new version instead. Mirrors the SQLite
# schema, with Postgres types (JSONB report, DOUBLE PRECISION timestamps).
MIGRATIONS: list[tuple[int, list[str]]] = [
    (
        1,
        [
            """
            CREATE TABLE IF NOT EXISTS scans (
                id TEXT PRIMARY KEY,
                target TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at DOUBLE PRECISION NOT NULL,
                finished_at DOUBLE PRECISION,
                result JSONB,
                error TEXT,
                provider TEXT,
                risk_score DOUBLE PRECISION,
                severity TEXT,
                recommendation TEXT
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_scans_created_at ON scans (created_at DESC)",
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                scan_retention_days DOUBLE PRECISION
            )
            """,
        ],
    ),
    (
        2,
        [
            """
            CREATE TABLE scan_log_lines (
                id BIGSERIAL PRIMARY KEY,
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
                created_at DOUBLE PRECISION NOT NULL
            )
            """,
            """
            CREATE TABLE sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at DOUBLE PRECISION NOT NULL,
                expires_at DOUBLE PRECISION NOT NULL
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
                created_at DOUBLE PRECISION NOT NULL,
                expires_at DOUBLE PRECISION NOT NULL,
                used_at DOUBLE PRECISION
            )
            """,
            "CREATE INDEX idx_password_resets_user ON password_resets (user_id)",
        ],
    ),
    (
        5,
        [
            "ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'",
            "ALTER TABLE users ADD COLUMN last_login_at DOUBLE PRECISION",
            "ALTER TABLE app_settings ADD COLUMN allow_signup BOOLEAN",
            """
            CREATE TABLE audit_log (
                id BIGSERIAL PRIMARY KEY,
                created_at DOUBLE PRECISION NOT NULL,
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
                created_at DOUBLE PRECISION NOT NULL,
                updated_at DOUBLE PRECISION NOT NULL
            )
            """,
            """
            CREATE TABLE scan_secrets (
                scan_id TEXT PRIMARY KEY,
                encrypted_key TEXT NOT NULL,
                created_at DOUBLE PRECISION NOT NULL
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
                id BIGSERIAL PRIMARY KEY,
                key TEXT NOT NULL,
                hit_at DOUBLE PRECISION NOT NULL,
                expires_at DOUBLE PRECISION NOT NULL
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
            "ALTER TABLE app_settings ADD COLUMN scans_paused BOOLEAN",
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
                created_at DOUBLE PRECISION NOT NULL,
                expires_at DOUBLE PRECISION,
                last_used_at DOUBLE PRECISION
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
            "ALTER TABLE scans ADD COLUMN badge BOOLEAN NOT NULL DEFAULT FALSE",
        ],
    ),
    (
        19,
        [
            # What the health panel and alerts read (app/monitoring.py): failed scans, sign-in
            # lockouts, and the alerts sent. Kept 30 days.
            """
            CREATE TABLE monitor_events (
                id BIGSERIAL PRIMARY KEY,
                created_at DOUBLE PRECISION NOT NULL,
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
                created_at DOUBLE PRECISION NOT NULL,
                updated_at DOUBLE PRECISION NOT NULL,
                PRIMARY KEY (user_id, provider)
            )
            """,
            # The scan reads a private repository, with its owner's connection: its result stays
            # theirs (no share link or badge unless they confirm, and only they open it).
            "ALTER TABLE scans ADD COLUMN private_source BOOLEAN NOT NULL DEFAULT FALSE",
        ],
    ),
    (
        23,
        [
            # Apply the baseline the scanned skill ships, if any (app/scan_runner.py's
            # shipped_baseline): the user opted in.
            "ALTER TABLE scans ADD COLUMN use_shipped_baseline BOOLEAN NOT NULL DEFAULT FALSE",
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
                created_at DOUBLE PRECISION NOT NULL,
                expires_at DOUBLE PRECISION NOT NULL
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
            # Accounts made with GitHub have no password.
            "ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL",
            # Ways to sign in other than a password (app/auth/github_sign_in.py): GitHub, by its
            # numeric user ID, which a rename doesn't change. display_name is only for the Account page.
            """
            CREATE TABLE user_identities (
                provider TEXT NOT NULL,
                provider_user_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                display_name TEXT,
                created_at DOUBLE PRECISION NOT NULL,
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


class PostgresStore:
    def __init__(self, url: str, *, default_retention_days: float | None) -> None:
        # Small pool: each process holds its own.
        self._pool = ConnectionPool(
            url,
            min_size=1,
            max_size=5,
            kwargs={"autocommit": True, "row_factory": dict_row},
            open=True,
        )
        self._migrate()
        self._execute(
            "INSERT INTO app_settings (id, scan_retention_days) VALUES (1, %s) ON CONFLICT (id) DO NOTHING",
            (default_retention_days,),
        )

    def _migrate(self) -> None:
        with self._pool.connection() as conn, conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (_MIGRATION_LOCK_ID,))
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations"
                " (version INTEGER PRIMARY KEY, applied_at DOUBLE PRECISION NOT NULL)"
            )
            applied = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}
            for version, statements in MIGRATIONS:
                if version in applied:
                    continue
                for statement in statements:
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (%s, %s)",
                    (version, time.time()),
                )

    def _execute(self, query: str, params: tuple[Any, ...] = ()) -> int:
        with self._pool.connection() as conn:
            return conn.execute(query, params).rowcount

    def close(self) -> None:
        self._pool.close()

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
        with self._pool.connection() as conn, conn.transaction():
            if max_active is not None and owner_id is not None:
                # One count and insert at a time per user: under READ COMMITTED, two at once would
                # both count before either inserts.
                conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"active-scans:{owner_id}",))
                active = conn.execute(
                    "SELECT COUNT(*) AS active FROM scans WHERE owner_id = %s AND status IN ('pending', 'running')", (owner_id,)
                ).fetchone()["active"]
                if active >= max_active:
                    return None
            conn.execute(insert_scan_query("%s", max_active=None), values)
            # The counter's row lock orders concurrent inserts for the same owner.
            report_no = conn.execute(NEXT_REPORT_NO.format(p="%s"), (owner_id or "",)).fetchone()["last_no"]
            conn.execute("UPDATE scans SET report_no = %s WHERE id = %s", (report_no, id))
        return report_no

    def update_scan(
        self,
        *,
        id: str,
        status: str,
        finished_at: float | None,
        result: dict[str, Any] | None,
        error: str | None,
    ) -> None:
        self._execute(
            """
            UPDATE scans
            SET status = %s, finished_at = %s, result = %s, error = %s,
                risk_score = %s, severity = %s, recommendation = %s, ai_review = %s,
                ai_input_tokens = %s, ai_output_tokens = %s, ai_cached_tokens = %s
            WHERE id = %s
            """,
            (
                status,
                finished_at,
                Jsonb(result) if result is not None else None,
                error,
                *summary_columns(result),
                id,
            ),
        )

    def start_attempt(self, scan_id: str) -> int:
        with self._pool.connection() as conn:
            row = conn.execute("UPDATE scans SET attempts = attempts + 1 WHERE id = %s RETURNING attempts", (scan_id,)).fetchone()
        return int(row["attempts"]) if row else 0

    def unfinished_scans(self) -> list[ScanRow]:
        with self._pool.connection() as conn:
            return list(conn.execute("SELECT * FROM scans WHERE status IN ('pending', 'running') ORDER BY created_at").fetchall())

    def fail_unfinished_scans(self, *, error: str, finished_at: float) -> int:
        return self._execute(
            "UPDATE scans SET status = 'error', error = %s, finished_at = %s WHERE status IN ('pending', 'running')",
            (error, finished_at),
        )

    def count_active_scans(self, *, owner_id: str | None = None) -> int:
        where, params = (" AND owner_id = %s", (owner_id,)) if owner_id is not None else ("", ())
        query = f"SELECT COUNT(*) AS active FROM scans WHERE status IN ('pending', 'running'){where}"
        with self._pool.connection() as conn:
            row = conn.execute(query, params).fetchone()
        return row["active"]

    def ai_token_totals(self, *, since: float, owner_id: str | None = None) -> dict[str, int]:
        where, params = (" AND owner_id = %s", (owner_id,)) if owner_id is not None else ("", ())
        query = f"""
            SELECT COUNT(ai_input_tokens) AS scans, COALESCE(SUM(ai_input_tokens), 0) AS input_tokens,
                   COALESCE(SUM(ai_output_tokens), 0) AS output_tokens, COALESCE(SUM(ai_cached_tokens), 0) AS cached_tokens
            FROM scans WHERE created_at >= %s{where}
        """
        with self._pool.connection() as conn:
            row = conn.execute(query, (since, *params)).fetchone()
        # SUM over BIGINT is NUMERIC in Postgres.
        return {key: int(value) for key, value in row.items()}

    def get_scan(self, id: str) -> ScanRow | None:
        with self._pool.connection() as conn:
            return conn.execute("SELECT * FROM scans WHERE id = %s", (id,)).fetchone()

    def previous_scan(
        self, *, target: str, owner_id: str | None, before: float, with_ai_review: bool, columns: str = "*"
    ) -> ScanRow | None:
        query, params = previous_scan_query(
            "%s", target=target, owner_id=owner_id, before=before, with_ai_review=with_ai_review, columns=columns
        )
        with self._pool.connection() as conn:
            return conn.execute(query, params).fetchone()

    def set_share_token(self, scan_id: str, token_hash: str | None, token_secret: str | None) -> None:
        with self._pool.connection() as conn:
            # An unshared scan is off its badge too.
            conn.execute(
                "UPDATE scans SET share_token = NULL, share_token_hash = %s, share_token_secret = %s, badge = badge AND %s WHERE id = %s",
                (token_hash, token_secret, token_hash is not None, scan_id),
            )

    def plain_share_tokens(self) -> list[tuple[str, str]]:
        with self._pool.connection() as conn:
            rows = conn.execute("SELECT id, share_token FROM scans WHERE share_token IS NOT NULL").fetchall()
        return [(row["id"], row["share_token"]) for row in rows]

    def get_shared_scan(self, token_hash: str) -> ScanRow | None:
        with self._pool.connection() as conn:
            return conn.execute("SELECT * FROM scans WHERE share_token_hash = %s", (token_hash,)).fetchone()

    def set_badge(self, scan_id: str, on: bool) -> None:
        with self._pool.connection() as conn:
            conn.execute("UPDATE scans SET badge = %s WHERE id = %s", (on, scan_id))

    def badge_scan(self, target: str) -> ScanRow | None:
        with self._pool.connection() as conn:
            return conn.execute(badge_scan_query("%s"), (target,)).fetchone()

    def delete_scan(self, id: str) -> bool:
        with self._pool.connection() as conn, conn.transaction():
            deleted = conn.execute("DELETE FROM scans WHERE id = %s", (id,)).rowcount
            conn.execute("DELETE FROM scan_log_lines WHERE scan_id = %s", (id,))
            conn.execute("DELETE FROM scan_secrets WHERE scan_id = %s", (id,))
        return deleted > 0

    def prune_account_records(self, *, audit_cutoff: float, now: float) -> int:
        with self._pool.connection() as conn, conn.transaction():
            deleted = conn.execute("DELETE FROM audit_log WHERE created_at < %s", (audit_cutoff,)).rowcount
            conn.execute("DELETE FROM password_resets WHERE expires_at < %s", (now,))
            conn.execute("DELETE FROM pending_signups WHERE expires_at < %s", (now,))
        return deleted

    def delete_scans_older_than(self, cutoff: float) -> int:
        # Pending/running scans are still owned by a live job; deleting them would lose the result.
        # Their log lines and secrets first, found by the same condition through the indexes, so the
        # sweep touches only the rows it deletes. (A data-modifying CTE would hide from the planner how
        # few scans expire, and it would read the log lines in full.)
        expired = "SELECT id FROM scans WHERE created_at < %s AND status NOT IN ('pending', 'running')"
        with self._pool.connection() as conn, conn.transaction():
            conn.execute(f"DELETE FROM scan_log_lines WHERE scan_id IN ({expired})", (cutoff,))
            conn.execute(f"DELETE FROM scan_secrets WHERE scan_id IN ({expired})", (cutoff,))
            return conn.execute("DELETE FROM scans WHERE created_at < %s AND status NOT IN ('pending', 'running')", (cutoff,)).rowcount

    def get_retention_days(self) -> float | None:
        with self._pool.connection() as conn:
            row = conn.execute("SELECT scan_retention_days FROM app_settings WHERE id = 1").fetchone()
        return row["scan_retention_days"] if row else None

    def set_retention_days(self, value: float | None) -> None:
        self._execute("UPDATE app_settings SET scan_retention_days = %s WHERE id = 1", (value,))

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
        where, params = scan_filter("%s", owner_id=owner_id, target=target)
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {SUMMARY_COLUMNS} FROM scans {where} {scan_order(sort, order)} LIMIT %s OFFSET %s",
                (*params, limit, offset),
            ).fetchall()
            total = conn.execute(f"SELECT COUNT(*) AS total FROM scans {where}", params).fetchone()["total"]
        return rows, total

    def append_log_lines(self, scan_id: str, lines: list[str], *, keep: int, steps: int = 0) -> None:
        with self._pool.connection() as conn, conn.transaction():
            if steps:
                conn.execute("UPDATE scans SET completed_steps = completed_steps + %s WHERE id = %s", (steps, scan_id))
            if not lines:
                return
            with conn.cursor() as cursor:
                cursor.executemany("INSERT INTO scan_log_lines (scan_id, line) VALUES (%s, %s)", [(scan_id, line) for line in lines])
            # Keep only the newest `keep` lines of this scan.
            conn.execute(
                """
                DELETE FROM scan_log_lines
                WHERE scan_id = %s AND id <= (
                    SELECT id FROM scan_log_lines WHERE scan_id = %s ORDER BY id DESC LIMIT 1 OFFSET %s
                )
                """,
                (scan_id, scan_id, keep),
            )

    def get_log_lines(self, scan_id: str) -> list[str]:
        with self._pool.connection() as conn:
            rows = conn.execute("SELECT line FROM scan_log_lines WHERE scan_id = %s ORDER BY id", (scan_id,)).fetchall()
        return [row["line"] for row in rows]

    def get_log_lines_after(self, scan_id: str, after: int) -> list[tuple[int, str]]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, line FROM scan_log_lines WHERE scan_id = %s AND id > %s ORDER BY id", (scan_id, after)
            ).fetchall()
        return [(row["id"], row["line"]) for row in rows]

    def increment_progress(self, scan_id: str) -> None:
        self._execute("UPDATE scans SET completed_steps = completed_steps + 1 WHERE id = %s", (scan_id,))

    def get_progress(self, scan_id: str) -> int:
        with self._pool.connection() as conn:
            row = conn.execute("SELECT completed_steps FROM scans WHERE id = %s", (scan_id,)).fetchone()
        return row["completed_steps"] if row else 0

    def clear_logs(self, scan_id: str) -> None:
        with self._pool.connection() as conn, conn.transaction():
            conn.execute("DELETE FROM scan_log_lines WHERE scan_id = %s", (scan_id,))
            conn.execute("UPDATE scans SET completed_steps = 0 WHERE id = %s", (scan_id,))

    # Accounts (app/auth). Emails are stored lower-cased by the caller.

    def create_user(self, *, id: str, email: str, password_hash: str | None, role: str, created_at: float) -> None:
        self._execute(
            "INSERT INTO users (id, email, password_hash, role, created_at) VALUES (%s, %s, %s, %s, %s)",
            (id, email, password_hash, role, created_at),
        )

    def create_first_user(self, *, id: str, email: str, password_hash: str, role: str, created_at: float) -> bool:
        """Create the account only if none exists yet; False when another request got there first."""
        with self._pool.connection() as conn, conn.transaction():
            # Serialise concurrent first-run setups so only one of them creates the admin.
            conn.execute("LOCK TABLE users IN EXCLUSIVE MODE")
            if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                return False
            conn.execute(
                "INSERT INTO users (id, email, password_hash, role, created_at) VALUES (%s, %s, %s, %s, %s)",
                (id, email, password_hash, role, created_at),
            )
        return True

    def get_user(self, id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            return conn.execute("SELECT * FROM users WHERE id = %s", (id,)).fetchone()

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            return conn.execute("SELECT * FROM users WHERE email = %s", (email,)).fetchone()

    def list_users(self, *, query: str | None = None) -> list[dict[str, Any]]:
        where, params = ("WHERE users.email LIKE %s", (f"%{query.lower()}%",)) if query else ("", ())
        with self._pool.connection() as conn:
            return conn.execute(
                f"""
                SELECT users.id, users.email, users.role, users.status, users.created_at, users.last_login_at,
                       users.daily_scan_quota, users.concurrent_scan_quota,
                       COALESCE(counts.scans, 0) AS scan_count
                FROM users
                LEFT JOIN (SELECT owner_id, COUNT(*) AS scans FROM scans GROUP BY owner_id) AS counts
                    ON counts.owner_id = users.id
                {where}
                ORDER BY users.created_at
                """,
                params,
            ).fetchall()

    def count_users(self) -> int:
        with self._pool.connection() as conn:
            return conn.execute("SELECT COUNT(*) AS users FROM users").fetchone()["users"]

    def delete_user(self, id: str) -> list[str] | None:
        with self._pool.connection() as conn, conn.transaction():
            if conn.execute("SELECT 1 FROM users WHERE id = %s FOR UPDATE", (id,)).fetchone() is None:
                return None
            uploads = [row["upload"] for row in conn.execute("SELECT upload FROM scans WHERE owner_id = %s AND upload IS NOT NULL", (id,))]
            conn.execute("DELETE FROM scan_log_lines WHERE scan_id IN (SELECT id FROM scans WHERE owner_id = %s)", (id,))
            conn.execute("DELETE FROM scan_secrets WHERE scan_id IN (SELECT id FROM scans WHERE owner_id = %s)", (id,))
            conn.execute("DELETE FROM scans WHERE owner_id = %s", (id,))
            # Fixed names, never input.
            for table in ("sessions", "password_resets", "llm_credentials", "api_tokens", "repo_connections", "user_identities"):
                conn.execute(f"DELETE FROM {table} WHERE user_id = %s", (id,))
            conn.execute("UPDATE audit_log SET actor_email = NULL, detail = NULL WHERE actor_id = %s", (id,))
            conn.execute("UPDATE audit_log SET target_email = NULL, detail = NULL WHERE target_id = %s", (id,))
            conn.execute("DELETE FROM report_counters WHERE owner = %s", (id,))
            conn.execute("DELETE FROM users WHERE id = %s", (id,))
        return uploads

    def set_repo_connection(self, *, user_id: str, provider: str, account_name: str, encrypted_token: str, now: float) -> None:
        self._execute(
            """
            INSERT INTO repo_connections (user_id, provider, account_name, encrypted_token, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, provider) DO UPDATE SET
                account_name = excluded.account_name, encrypted_token = excluded.encrypted_token, updated_at = excluded.updated_at
            """,
            (user_id, provider, account_name, encrypted_token, now, now),
        )

    def get_repo_connection(self, user_id: str, provider: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            return conn.execute("SELECT * FROM repo_connections WHERE user_id = %s AND provider = %s", (user_id, provider)).fetchone()

    def list_repo_connections(self, user_id: str) -> list[dict[str, Any]]:
        with self._pool.connection() as conn:
            return list(conn.execute("SELECT * FROM repo_connections WHERE user_id = %s ORDER BY provider", (user_id,)).fetchall())

    def delete_repo_connection(self, user_id: str, provider: str) -> bool:
        return self._execute("DELETE FROM repo_connections WHERE user_id = %s AND provider = %s", (user_id, provider)) > 0

    def create_api_token(self, *, id: str, user_id: str, name: str, token_hash: str, prefix: str, scopes: str, created_at: float, expires_at: float | None) -> None:
        self._execute(
            "INSERT INTO api_tokens (id, user_id, name, token_hash, prefix, scopes, created_at, expires_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (id, user_id, name, token_hash, prefix, scopes, created_at, expires_at),
        )

    def list_api_tokens(self, user_id: str) -> list[dict[str, Any]]:
        with self._pool.connection() as conn:
            return conn.execute(
                "SELECT id, user_id, name, prefix, scopes, created_at, expires_at, last_used_at FROM api_tokens WHERE user_id = %s ORDER BY created_at DESC", (user_id,)
            ).fetchall()

    def get_api_token_user(self, token_hash: str, *, now: float) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            return conn.execute(
                """
                SELECT users.id, users.email, users.role, users.status, users.created_at, users.last_login_at,
                       users.daily_scan_quota, users.concurrent_scan_quota,
                       api_tokens.id AS token_id, api_tokens.name AS token_name, api_tokens.scopes AS token_scopes,
                       api_tokens.last_used_at AS token_last_used_at
                FROM api_tokens JOIN users ON users.id = api_tokens.user_id
                WHERE api_tokens.token_hash = %s AND (api_tokens.expires_at IS NULL OR api_tokens.expires_at > %s)
                  AND users.status = 'active'
                """,
                (token_hash, now),
            ).fetchone()

    def mark_api_token_used(self, token_id: str, at: float) -> None:
        self._execute("UPDATE api_tokens SET last_used_at = %s WHERE id = %s", (at, token_id))

    def delete_api_tokens_for_user(self, user_id: str) -> int:
        return self._execute("DELETE FROM api_tokens WHERE user_id = %s", (user_id,))

    def delete_api_token(self, token_id: str, *, user_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn, conn.transaction():
            row = conn.execute(
                "SELECT id, user_id, name, prefix, scopes, created_at, expires_at, last_used_at FROM api_tokens WHERE id = %s AND user_id = %s", (token_id, user_id)
            ).fetchone()
            if row is not None:
                conn.execute("DELETE FROM api_tokens WHERE id = %s", (token_id,))
        return row

    def create_session(self, *, token_hash: str, user_id: str, created_at: float, expires_at: float) -> None:
        self._execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (%s, %s, %s, %s)",
            (token_hash, user_id, created_at, expires_at),
        )

    def get_session_user(self, token_hash: str, *, now: float) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            return conn.execute(
                """
                SELECT users.id, users.email, users.role, users.status, users.created_at, users.last_login_at,
                       users.daily_scan_quota, users.concurrent_scan_quota
                FROM sessions JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = %s AND sessions.expires_at > %s AND users.status = 'active'
                """,
                (token_hash, now),
            ).fetchone()

    def delete_session(self, token_hash: str) -> None:
        self._execute("DELETE FROM sessions WHERE token_hash = %s", (token_hash,))

    def get_session_created_at(self, token_hash: str) -> float | None:
        with self._pool.connection() as conn:
            row = conn.execute("SELECT created_at FROM sessions WHERE token_hash = %s", (token_hash,)).fetchone()
        return row["created_at"] if row else None

    def get_identity_user(self, provider: str, provider_user_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            return conn.execute(
                "SELECT users.* FROM user_identities JOIN users ON users.id = user_identities.user_id"
                " WHERE user_identities.provider = %s AND user_identities.provider_user_id = %s",
                (provider, provider_user_id),
            ).fetchone()

    def list_identities(self, user_id: str) -> list[dict[str, Any]]:
        with self._pool.connection() as conn:
            return conn.execute(
                "SELECT provider, display_name, created_at FROM user_identities WHERE user_id = %s ORDER BY provider", (user_id,)
            ).fetchall()

    def add_identity(self, *, provider: str, provider_user_id: str, user_id: str, display_name: str | None, created_at: float) -> bool:
        return self._execute(
            "INSERT INTO user_identities (provider, provider_user_id, user_id, display_name, created_at) VALUES (%s, %s, %s, %s, %s)"
            " ON CONFLICT DO NOTHING",
            (provider, provider_user_id, user_id, display_name, created_at),
        ) > 0

    def rename_identity(self, provider: str, provider_user_id: str, display_name: str | None) -> None:
        self._execute(
            "UPDATE user_identities SET display_name = %s WHERE provider = %s AND provider_user_id = %s", (display_name, provider, provider_user_id)
        )

    def delete_identity(self, user_id: str, provider: str) -> bool:
        return self._execute("DELETE FROM user_identities WHERE user_id = %s AND provider = %s", (user_id, provider)) > 0

    def delete_expired_sessions(self, now: float) -> int:
        return self._execute("DELETE FROM sessions WHERE expires_at <= %s", (now,))

    def set_password_hash(self, user_id: str, password_hash: str) -> None:
        self._execute("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id))

    def delete_sessions_for_user(self, user_id: str, *, keep_token_hash: str | None = None) -> None:
        self._execute(
            "DELETE FROM sessions WHERE user_id = %s AND token_hash IS DISTINCT FROM %s", (user_id, keep_token_hash)
        )

    def create_password_reset(self, *, token_hash: str, user_id: str, created_at: float, expires_at: float) -> None:
        # Only the newest link works: issuing one cancels the user's earlier links.
        with self._pool.connection() as conn, conn.transaction():
            conn.execute("DELETE FROM password_resets WHERE user_id = %s", (user_id,))
            conn.execute(
                "INSERT INTO password_resets (token_hash, user_id, created_at, expires_at) VALUES (%s, %s, %s, %s)",
                (token_hash, user_id, created_at, expires_at),
            )

    def consume_password_reset(self, token_hash: str, *, now: float) -> str | None:
        """Mark an unused, unexpired reset as used and return its user id, in one statement."""
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE password_resets SET used_at = %s
                WHERE token_hash = %s AND used_at IS NULL AND expires_at > %s
                RETURNING user_id
                """,
                (now, token_hash, now),
            ).fetchone()
        return row["user_id"] if row else None

    def create_pending_signup(self, *, token_hash: str, email: str, password_hash: str, created_at: float, expires_at: float) -> None:
        # Only the newest link works: signing up again cancels the address's earlier links.
        with self._pool.connection() as conn, conn.transaction():
            conn.execute("DELETE FROM pending_signups WHERE email = %s", (email,))
            conn.execute(
                "INSERT INTO pending_signups (token_hash, email, password_hash, created_at, expires_at) VALUES (%s, %s, %s, %s, %s)",
                (token_hash, email, password_hash, created_at, expires_at),
            )

    def consume_pending_signup(self, token_hash: str, *, now: float) -> dict[str, Any] | None:
        """Remove an unexpired pending sign-up and return its email and password hash, in one statement."""
        with self._pool.connection() as conn:
            row = conn.execute(
                "DELETE FROM pending_signups WHERE token_hash = %s AND expires_at > %s RETURNING email, password_hash",
                (token_hash, now),
            ).fetchone()
        return dict(row) if row else None

    def update_user(self, user_id: str, *, role: str | None = None, status: str | None = None) -> None:
        self._execute(
            "UPDATE users SET role = COALESCE(%s, role), status = COALESCE(%s, status) WHERE id = %s",
            (role, status, user_id),
        )

    def set_user_quotas(self, user_id: str, *, daily_scan_quota: int | None, concurrent_scan_quota: int | None) -> None:
        self._execute(
            "UPDATE users SET daily_scan_quota = %s, concurrent_scan_quota = %s WHERE id = %s",
            (daily_scan_quota, concurrent_scan_quota, user_id),
        )

    def record_login(self, user_id: str, at: float) -> None:
        self._execute("UPDATE users SET last_login_at = %s WHERE id = %s", (at, user_id))

    def count_active_admins(self) -> int:
        with self._pool.connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) AS admins FROM users WHERE role = 'admin' AND status = 'active'"
            ).fetchone()["admins"]

    def get_allow_signup(self) -> bool | None:
        with self._pool.connection() as conn:
            row = conn.execute("SELECT allow_signup FROM app_settings WHERE id = 1").fetchone()
        return None if row is None else row["allow_signup"]

    def set_allow_signup(self, value: bool | None) -> None:
        self._execute("UPDATE app_settings SET allow_signup = %s WHERE id = 1", (value,))

    def get_scan_limits(self) -> dict[str, Any]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT scans_paused, daily_scan_quota, concurrent_scan_quota FROM app_settings WHERE id = 1"
            ).fetchone()
        return dict(row) if row else {"scans_paused": None, "daily_scan_quota": None, "concurrent_scan_quota": None}

    def set_scan_limits(
        self, *, scans_paused: bool | None, daily_scan_quota: int | None, concurrent_scan_quota: int | None
    ) -> None:
        self._execute(
            "UPDATE app_settings SET scans_paused = %s, daily_scan_quota = %s, concurrent_scan_quota = %s WHERE id = 1",
            (scans_paused, daily_scan_quota, concurrent_scan_quota),
        )

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
        self._execute(
            """
            INSERT INTO audit_log (created_at, actor_id, actor_email, action, target_id, target_email, detail)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (created_at, actor_id, actor_email, action, target_id, target_email, detail),
        )

    def add_monitor_event(self, *, created_at: float, kind: str, message: str | None, scan_id: str | None, count: int) -> None:
        self._execute(monitor_queries("%s")["add"], (created_at, kind, message, scan_id, count))

    def monitor_counts(self, *, since: float) -> dict[str, int]:
        with self._pool.connection() as conn:
            rows = conn.execute(monitor_queries("%s")["counts"], (since,)).fetchall()
        return {row["kind"]: int(row["total"]) for row in rows}

    def scan_outcomes(self, *, since: float) -> dict[str, int]:
        with self._pool.connection() as conn:
            row = conn.execute(monitor_queries("%s")["outcomes"], (since, since, since)).fetchone()
        return {key: int(row[key]) for key in ("started", "finished", "failed")}

    def last_monitor_event(self, kinds: tuple[str, ...], message: str | None = None) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            return conn.execute(*last_monitor_event_query("%s", kinds, message)).fetchone()

    def delete_monitor_events_older_than(self, cutoff: float) -> int:
        return self._execute(monitor_queries("%s")["prune"], (cutoff,))

    def list_monitor_events(self, limit: int, offset: int, kinds: tuple[str, ...]) -> tuple[list[dict[str, Any]], int]:
        rows_query, count_query = list_monitor_events_query("%s", kinds)
        with self._pool.connection() as conn:
            rows = conn.execute(rows_query, (*kinds, limit, offset)).fetchall()
            total = conn.execute(count_query, kinds).fetchone()["total"]
        return list(rows), int(total)

    def list_audit(self, limit: int, offset: int, *, target_id: str | None = None) -> tuple[list[dict[str, Any]], int]:
        where, params = ("WHERE target_id = %s", (target_id,)) if target_id else ("", ())
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM audit_log {where} ORDER BY id DESC LIMIT %s OFFSET %s", (*params, limit, offset)
            ).fetchall()
            total = conn.execute(f"SELECT COUNT(*) AS total FROM audit_log {where}", params).fetchone()["total"]
        return rows, total

    def overview_stats(self, *, since: float) -> dict[str, Any]:
        with self._pool.connection() as conn:
            users = conn.execute(
                """
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE role = 'admin') AS admins,
                       COUNT(*) FILTER (WHERE status = 'suspended') AS suspended,
                       COUNT(*) FILTER (WHERE created_at >= %s) AS new
                FROM users
                """,
                (since,),
            ).fetchone()
            scans = conn.execute(
                """
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE created_at >= %s) AS recent,
                       COUNT(*) FILTER (WHERE recommendation = 'DO_NOT_INSTALL') AS do_not_install,
                       COUNT(*) FILTER (WHERE recommendation = 'CAUTION') AS caution,
                       COUNT(*) FILTER (WHERE recommendation = 'SAFE') AS safe,
                       COUNT(*) FILTER (WHERE status = 'error') AS failed,
                       COUNT(*) FILTER (WHERE status IN ('pending', 'running')) AS active
                FROM scans
                """,
                (since,),
            ).fetchone()
        return {"users": users, "scans": scans}

    # Stored AI provider keys (encrypted by the caller; see app/secrets_box.py).

    def set_llm_credential(
        self, *, user_id: str, provider: str, encrypted_key: str, key_hint: str, now: float
    ) -> None:
        self._execute(
            """
            INSERT INTO llm_credentials (user_id, provider, encrypted_key, key_hint, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                provider = excluded.provider, encrypted_key = excluded.encrypted_key,
                key_hint = excluded.key_hint, updated_at = excluded.updated_at
            """,
            (user_id, provider, encrypted_key, key_hint, now, now),
        )

    def get_llm_credential(self, user_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            return conn.execute("SELECT * FROM llm_credentials WHERE user_id = %s", (user_id,)).fetchone()

    def delete_llm_credential(self, user_id: str) -> bool:
        return self._execute("DELETE FROM llm_credentials WHERE user_id = %s", (user_id,)) > 0

    def put_scan_secret(self, *, scan_id: str, encrypted_key: str, now: float) -> None:
        self._execute(
            """
            INSERT INTO scan_secrets (scan_id, encrypted_key, created_at) VALUES (%s, %s, %s)
            ON CONFLICT (scan_id) DO UPDATE SET encrypted_key = excluded.encrypted_key
            """,
            (scan_id, encrypted_key, now),
        )

    def get_scan_secret(self, scan_id: str) -> str | None:
        with self._pool.connection() as conn:
            row = conn.execute("SELECT encrypted_key FROM scan_secrets WHERE scan_id = %s", (scan_id,)).fetchone()
        return row["encrypted_key"] if row else None

    def delete_scan_secret(self, scan_id: str) -> None:
        self._execute("DELETE FROM scan_secrets WHERE scan_id = %s", (scan_id,))

    # Rate limits shared by every instance (app/rate_limit.py), and daily scan quotas (app/quotas.py).

    def count_rate_limit_hits(self, key: str, *, window_seconds: float, now: float) -> int:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS hits FROM rate_limit_hits WHERE key = %s AND hit_at > %s",
                (key, now - window_seconds),
            ).fetchone()
        return row["hits"]

    def rate_limit_hit(self, key: str, *, limit: int, window_seconds: float, now: float) -> float | None:
        with self._pool.connection() as conn, conn.transaction():
            # One check at a time per key, so concurrent requests can't both take the last slot.
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,))
            conn.execute("DELETE FROM rate_limit_hits WHERE expires_at <= %s", (now,))
            recent = conn.execute(
                "SELECT hit_at FROM rate_limit_hits WHERE key = %s AND hit_at > %s ORDER BY hit_at DESC LIMIT %s",
                (key, now - window_seconds, limit),
            ).fetchall()
            if len(recent) >= limit:
                return recent[-1]["hit_at"] + window_seconds - now
            conn.execute(
                "INSERT INTO rate_limit_hits (key, hit_at, expires_at) VALUES (%s, %s, %s)",
                (key, now, now + window_seconds),
            )
            return None

    def rate_limit_forget(self, key: str) -> None:
        self._execute(
            "DELETE FROM rate_limit_hits WHERE id = (SELECT id FROM rate_limit_hits WHERE key = %s ORDER BY hit_at DESC LIMIT 1)",
            (key,),
        )
