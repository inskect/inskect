from __future__ import annotations

from app.core.config import Settings
from app.storage.base import ScanRow, ScanStore

__all__ = ["ScanRow", "ScanStore", "create_store", "is_postgres_url"]

_POSTGRES_SCHEMES = ("postgres://", "postgresql://")


def is_postgres_url(url: str) -> bool:
    return url.startswith(_POSTGRES_SCHEMES)


def create_store(settings: Settings) -> ScanStore:
    """Postgres when INSKECT_DATABASE_URL is set, otherwise the SQLite file at db_path."""
    if settings.database_url:
        if not is_postgres_url(settings.database_url):
            raise ValueError("INSKECT_DATABASE_URL must be a postgres:// or postgresql:// URL")
        # Imported lazily so SQLite-only installs never load the Postgres driver.
        from app.storage.postgres import PostgresStore

        return PostgresStore(settings.database_url, default_retention_days=settings.scan_retention_days)

    from app.storage.sqlite import SQLiteStore

    return SQLiteStore(settings.db_path, default_retention_days=settings.scan_retention_days)
