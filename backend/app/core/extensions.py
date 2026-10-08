"""The pieces a deployment may replace (docs/EXTENDING.md), each a class named by its import path,
`module:Class`, in a setting: how scans are queued (INSKECT_JOB_RUNNER), where they run
(INSKECT_SCAN_EXECUTOR), and where uploads are held (INSKECT_UPLOAD_STORE).
"""

from __future__ import annotations

import importlib
from typing import Any


class ExtensionError(RuntimeError):
    """A setting names a class that can't be loaded; the API refuses to start."""


def load(path: str, setting: str) -> Any:
    """An instance of the class at path, made with no arguments."""
    module_name, _, name = path.partition(":")
    if not module_name or not name:
        raise ExtensionError(f"{setting} must name a class as module:Class, not {path!r}")
    try:
        factory = getattr(importlib.import_module(module_name), name)
    except (ImportError, AttributeError) as exc:
        raise ExtensionError(f"{setting}={path} can't be loaded: {exc}") from exc
    return factory()
