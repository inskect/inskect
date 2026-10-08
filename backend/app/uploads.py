"""Skills uploaded from the browser: a .zip, or a .md file on its own, held only while it's scanned.

The API receives the file and hands it to the upload store (INSKECT_UPLOAD_STORE, see
UploadStore), by default LocalUploadStore, which keeps it under data/uploads/<scan>.

A scan's target is `upload:<file name>`, and its `upload` column holds the store's reference to the
file. The file is deleted when the scan ends, whatever its outcome; ones a scan never got to are
swept on startup.
"""

from __future__ import annotations

import io
import logging
import re
import shutil
import zipfile
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Protocol

from app.core import extensions
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# The target a scan of an upload is recorded with: the file's name, after this prefix.
TARGET_PREFIX = "upload:"
# The local store's limit, compressed; skillspector's own limits then apply to what a zip unpacks to.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
SUFFIXES = (".zip", ".md")

_SAFE_NAME = re.compile(r"[^\w.\- ()]+")


class UploadRejectedError(ValueError):
    """An upload that can't be scanned, with the reason to show."""


class UploadStore(Protocol):
    """Where an uploaded file is held from when its scan is queued until it ends."""

    # Its name, which /health reports, and the largest file it takes.
    kind: str
    max_bytes: int

    def save(self, scan_id: str, name: str, data: bytes) -> str:
        """Keep the file for its scan (called in a thread); the reference to store with the scan."""

    async def read(self, ref: str) -> bytes:
        """The file's content."""

    def local_copy(self, ref: str, name: str) -> AbstractAsyncContextManager[str]:
        """A path on this machine holding the file under its own name, for as long as it's open."""

    async def delete(self, ref: str) -> None:
        """Delete the file; it may raise, the caller logs it."""

    def clear(self, keep: set[str] | frozenset[str]) -> None:
        """On startup, before any scan runs: delete the files of every scan but these."""


@lru_cache
def get_store() -> UploadStore:
    return extensions.load(get_settings().upload_store, "INSKECT_UPLOAD_STORE")


def store_kind(settings: Settings | None = None) -> str:
    """Where uploads are held, for the scan form and the GitHub Action."""
    return get_store().kind


def max_bytes() -> int:
    return get_store().max_bytes


def save(scan_id: str, name: str, data: bytes) -> str:
    return get_store().save(scan_id, name, data)


def clear(keep: set[str] | frozenset[str] = frozenset()) -> None:
    get_store().clear(keep)


def target_for(name: str) -> str:
    return TARGET_PREFIX + name


def is_upload_target(target: str) -> bool:
    return target.startswith(TARGET_PREFIX)


def safe_name(name: str) -> str:
    """The uploaded file's own name, without folders or odd characters; refused unless .zip or .md."""
    base = PurePosixPath(name.replace("\\", "/")).name
    base = _SAFE_NAME.sub("_", base).strip(" .")[:100]
    if not base.lower().endswith(SUFFIXES):
        raise UploadRejectedError("Upload a .zip of the skill, or its SKILL.md")
    return base


def check_content(name: str, data: bytes) -> None:
    """Refuse an upload skillspector can't scan, with the reason, before it's queued.

    skillspector checks a zip again when it unpacks it (sizes, entry count, paths); this catches a
    broken or oversized one early, with a message, rather than as a failed scan.
    """
    from skillspector.input_handler import INGEST_MAX_BYTES, INGEST_MAX_ZIP_MEMBERS

    if not data:
        raise UploadRejectedError(f"{name} is empty")
    limit = max_bytes()
    if len(data) > limit:
        raise UploadRejectedError(f"{name} is larger than {limit // (1024 * 1024)} MB")
    if not name.lower().endswith(".zip"):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UploadRejectedError(f"{name} isn't a text file") from exc
        return
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
    except (zipfile.BadZipFile, ValueError) as exc:
        raise UploadRejectedError(f"{name} isn't a valid zip archive") from exc
    if not any(not member.is_dir() for member in members):
        raise UploadRejectedError(f"{name} holds no files")
    if len(members) > INGEST_MAX_ZIP_MEMBERS:
        raise UploadRejectedError(f"{name} holds more than {INGEST_MAX_ZIP_MEMBERS} entries")
    if sum(member.file_size for member in members) > INGEST_MAX_BYTES:
        raise UploadRejectedError(f"{name} unpacks to more than {INGEST_MAX_BYTES // (1024 * 1024)} MB")
    for member in members:
        path = PurePosixPath(member.filename.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts:
            raise UploadRejectedError(f"{name} holds a file outside the archive: {member.filename}")


# Local store.


def _local_root() -> Path:
    return Path(get_settings().db_path).parent / "uploads"


def save_local(scan_id: str, name: str, data: bytes) -> str:
    """Keep an upload for its scan; the reference to store with the scan."""
    folder = _local_root() / scan_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(data)
    return str(path)


def clear_local(keep: set[str] | frozenset[str] = frozenset()) -> None:
    """Delete the local uploads of every scan but these: on startup, when no scan is running, those
    of the scans that will be run again."""
    root = _local_root()
    if not keep:
        shutil.rmtree(root, ignore_errors=True)
        return
    for entry in root.glob("*") if root.is_dir() else ():
        if entry.name in keep:
            continue
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            entry.unlink(missing_ok=True)


class LocalUploadStore:
    """The default: files under data/uploads/<scan>, next to the SQLite database."""

    kind = "local"
    max_bytes = MAX_UPLOAD_BYTES

    def save(self, scan_id: str, name: str, data: bytes) -> str:
        return save_local(scan_id, name, data)

    async def read(self, ref: str) -> bytes:
        return Path(ref).read_bytes()

    @asynccontextmanager
    async def local_copy(self, ref: str, name: str) -> AsyncIterator[str]:
        yield ref

    async def delete(self, ref: str) -> None:
        folder = Path(ref).resolve().parent
        # Only ever a scan's own folder of uploads.
        if folder.parent == _local_root().resolve():
            shutil.rmtree(folder, ignore_errors=True)

    def clear(self, keep: set[str] | frozenset[str]) -> None:
        clear_local(keep)


# Whichever store.


async def read(ref: str) -> bytes:
    return await get_store().read(ref)


@asynccontextmanager
async def local_copy(ref: str, name: str) -> AsyncIterator[str]:
    """A path on this machine holding the upload, under its own name (skillspector goes by the suffix)."""
    async with get_store().local_copy(ref, name) as path:
        yield path


async def delete(ref: str | None) -> None:
    """Delete a scan's upload. Never raises: the scan's outcome matters more than a leftover file."""
    if not ref:
        return
    try:
        await get_store().delete(ref)
    except Exception:
        logger.warning("Couldn't delete the upload %s; the next startup will", ref, exc_info=True)
