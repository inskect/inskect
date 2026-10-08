"""Live log lines and step progress for running scans.

Two stores, picked from INSKECT_LOG_STORE: `memory` (lost on restart, the default with
SQLite) and `database` (the scan database, so whichever process serves the result page sees what
the one running the scan wrote; the default with Postgres).
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict, deque
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Literal, Protocol

from app import db
from app.core.config import Settings, get_settings

_MAX_LINES_PER_SCAN = 500
_MAX_TRACKED_SCANS = 50
# The database store writes pending lines this often, or as soon as this many are waiting.
_FLUSH_SECONDS = 1.0
_FLUSH_LINES = 100

logger = logging.getLogger(__name__)

# A ContextVar rather than threading.local: LangGraph runs parallel nodes (the analyzers fanned
# out from build_context) on worker threads, and copies the caller's context into them.
_current_job: ContextVar[str | None] = ContextVar("scan_logs_current_job", default=None)

LogStoreKind = Literal["memory", "database"]


class LogStore(Protocol):
    def append(self, job_id: str, message: str) -> None: ...

    def increment_progress(self, job_id: str) -> None: ...

    def get_progress(self, job_id: str) -> int: ...

    def listed_progress(self, job_id: str, stored: int) -> int: ...

    def get_logs(self, job_id: str) -> list[str]: ...

    def get_logs_after(self, job_id: str, after: int) -> tuple[list[str], int]: ...

    def forget(self, job_id: str) -> None: ...

    def flush(self, job_id: str) -> None: ...

    def close(self) -> None: ...


def _after(entries: list[tuple[int, str]], after: int) -> tuple[list[str], int]:
    """The lines, and the cursor to read on from: the last one's number, or `after` again."""
    return [line for _, line in entries], entries[-1][0] if entries else after


class MemoryLogStore:
    """The last 500 lines of the 50 most recently active scans, in this process."""

    def __init__(self) -> None:
        # Each line with its number, counted across every scan as the database's ids are, so a
        # scan run again doesn't reuse the numbers a page already read.
        self._buffers: OrderedDict[str, deque[tuple[int, str]]] = OrderedDict()
        self._progress: dict[str, int] = {}
        self._last_line = 0
        self._lock = threading.Lock()

    def _touch(self, job_id: str) -> None:
        """Track job_id as most-recently active; evict the oldest scan past the cap."""
        if job_id in self._buffers:
            self._buffers.move_to_end(job_id)
            return
        self._buffers[job_id] = deque(maxlen=_MAX_LINES_PER_SCAN)
        while len(self._buffers) > _MAX_TRACKED_SCANS:
            evicted, _ = self._buffers.popitem(last=False)
            self._progress.pop(evicted, None)

    def append(self, job_id: str, message: str) -> None:
        with self._lock:
            self._touch(job_id)
            self._last_line += 1
            self._buffers[job_id].append((self._last_line, message))

    def increment_progress(self, job_id: str) -> None:
        with self._lock:
            self._touch(job_id)
            self._progress[job_id] = self._progress.get(job_id, 0) + 1

    def get_progress(self, job_id: str) -> int:
        with self._lock:
            return self._progress.get(job_id, 0)

    def listed_progress(self, job_id: str, stored: int) -> int:
        return self.get_progress(job_id)

    def get_logs(self, job_id: str) -> list[str]:
        with self._lock:
            return [line for _, line in self._buffers.get(job_id, ())]

    def get_logs_after(self, job_id: str, after: int) -> tuple[list[str], int]:
        with self._lock:
            return _after([entry for entry in self._buffers.get(job_id, ()) if entry[0] > after], after)

    def forget(self, job_id: str) -> None:
        with self._lock:
            self._buffers.pop(job_id, None)
            self._progress.pop(job_id, None)

    def flush(self, job_id: str) -> None:
        return None

    def close(self) -> None:
        return None


@dataclass
class _Pending:
    """A scan's lines and steps not written yet."""

    lines: deque[str] = field(default_factory=lambda: deque(maxlen=_MAX_LINES_PER_SCAN))
    steps: int = 0


class DatabaseLogStore:
    """Log lines and step counts stored alongside the scan, capped at 500 lines per scan.

    Lines go away with their scan: deleting it or the retention sweep removes them too.

    Written in batches: a scan logs hundreds of lines, which one transaction each would make hundreds
    of round trips to the database. A thread writes what's pending about every second (sooner past
    100 lines), still faster than a result page polls; the scan's end writes the rest (flush), and
    reading a scan's log or progress here writes its pending lines first.
    """

    def __init__(self) -> None:
        self._pending: dict[str, _Pending] = {}
        self._lock = threading.Lock()
        # One write at a time, so a scan's batches land in order.
        self._write_lock = threading.Lock()
        self._wake = threading.Event()
        self._writer: threading.Thread | None = None

    def _add(self, job_id: str, *, line: str | None = None, steps: int = 0) -> None:
        with self._lock:
            pending = self._pending.setdefault(job_id, _Pending())
            if line is not None:
                pending.lines.append(line)
            pending.steps += steps
            full = len(pending.lines) >= _FLUSH_LINES
            if self._writer is None:
                self._writer = threading.Thread(target=self._write_pending, name="scan-log-writer", daemon=True)
                self._writer.start()
        if full:
            self._wake.set()

    def _write_pending(self) -> None:
        """The writer thread: writes every scan's pending lines each second, and stops once there
        are none (the next line starts it again)."""
        while True:
            self._wake.wait(_FLUSH_SECONDS)
            self._wake.clear()
            self._write(None)
            with self._lock:
                if not self._pending:
                    self._writer = None
                    return

    def _write(self, job_id: str | None) -> None:
        """Write job_id's pending lines and steps, or every scan's. A batch that fails is kept for
        the next try: a log line must never fail its scan."""
        with self._write_lock:
            with self._lock:
                if job_id is None:
                    batches, self._pending = self._pending, {}
                else:
                    batch = self._pending.pop(job_id, None)
                    batches = {job_id: batch} if batch else {}
            for scan_id, batch in batches.items():
                try:
                    db.append_log_lines(scan_id, list(batch.lines), keep=_MAX_LINES_PER_SCAN, steps=batch.steps)
                except Exception:
                    logger.warning("Couldn't write the log of scan %s; trying again", scan_id, exc_info=True)
                    with self._lock:
                        later = self._pending.get(scan_id)
                        if later is not None:
                            batch.lines.extend(later.lines)
                            batch.steps += later.steps
                        self._pending[scan_id] = batch

    def append(self, job_id: str, message: str) -> None:
        self._add(job_id, line=message)

    def increment_progress(self, job_id: str) -> None:
        self._add(job_id, steps=1)

    def get_progress(self, job_id: str) -> int:
        self._write(job_id)
        return db.get_progress(job_id)

    def listed_progress(self, job_id: str, stored: int) -> int:
        # With the steps counted here but not written yet: no query, and no write, per listed scan.
        with self._lock:
            pending = self._pending.get(job_id)
            return stored + (pending.steps if pending else 0)

    def get_logs(self, job_id: str) -> list[str]:
        self._write(job_id)
        return db.get_log_lines(job_id)

    def get_logs_after(self, job_id: str, after: int) -> tuple[list[str], int]:
        self._write(job_id)
        return _after(db.get_log_lines_after(job_id, after), after)

    def forget(self, job_id: str) -> None:
        with self._write_lock, self._lock:
            self._pending.pop(job_id, None)
        db.clear_logs(job_id)

    def flush(self, job_id: str) -> None:
        self._write(job_id)

    def close(self) -> None:
        """Write everything pending, and let the writer thread end: when the API stops (and between
        tests, so no line written late lands in the next one's database)."""
        self._write(None)
        with self._lock:
            writer = self._writer
        if writer is not None:
            self._wake.set()
            writer.join(timeout=_FLUSH_SECONDS * 5)


def log_store_kind(settings: Settings) -> LogStoreKind:
    """INSKECT_LOG_STORE when set, otherwise the database with Postgres."""
    if settings.log_store:
        return settings.log_store
    return "database" if settings.database_url else "memory"


def create_log_store(settings: Settings) -> LogStore:
    return DatabaseLogStore() if log_store_kind(settings) == "database" else MemoryLogStore()


_store: LogStore | None = None
_store_lock = threading.Lock()


def _get_store() -> LogStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = create_log_store(get_settings())
    return _store


def append(job_id: str, message: str) -> None:
    _get_store().append(job_id, message)


def increment_progress(job_id: str) -> None:
    _get_store().increment_progress(job_id)


def get_progress(job_id: str) -> int:
    return _get_store().get_progress(job_id)


def listed_progress(job_id: str, stored: int) -> int:
    """A listed scan's step count without a query per scan: `stored` is the row's completed_steps,
    where the database store keeps it; the memory store keeps its own."""
    return _get_store().listed_progress(job_id, stored)


def get_logs(job_id: str) -> list[str]:
    return _get_store().get_logs(job_id)


def get_logs_after(job_id: str, after: int) -> tuple[list[str], int]:
    """The scan's lines after cursor `after` (0 for all of them), and the cursor to read on from."""
    return _get_store().get_logs_after(job_id, after)


def forget(job_id: str) -> None:
    """Drop a scan's lines and progress: when it's deleted, or before it's run again."""
    _get_store().forget(job_id)


def flush(job_id: str) -> None:
    """Write the scan's lines and progress not written yet: when it ends."""
    _get_store().flush(job_id)


def close() -> None:
    """Write whatever is pending, when the API stops."""
    if _store is not None:
        _store.close()


class _JobLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        job_id = _current_job.get()
        if job_id is None:
            return
        try:
            append(job_id, self.format(record))
        except Exception:  # noqa: BLE001
            # A log line that can't be stored must never fail the scan that produced it.
            self.handleError(record)


def init_logging() -> None:
    """Attach the capture handler to skillspector's logger. Safe to call more than once."""
    logger = logging.getLogger("skillspector")
    logger.setLevel(logging.INFO)
    if any(isinstance(existing, _JobLogHandler) for existing in logger.handlers):
        return
    handler = _JobLogHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)


def start_capture(job_id: str) -> None:
    _current_job.set(job_id)


def stop_capture() -> None:
    _current_job.set(None)
