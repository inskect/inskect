"""Following a skill's external references, as skillspector's --transitive does.

skillspector follows references to the code hosts it can fetch from (Git repositories and raw
files, never /blob/ or /tree/ web pages), scans what it finds, and marks those findings with their
source and depth. Operators bound it with INSKECT_TRANSITIVE_* settings.
"""

from __future__ import annotations

from typing import Any

from app.core.config import Settings


def transitive_options(settings: Settings, depth: int | None) -> dict[str, Any] | None:
    """What app/scan_runner.py needs to follow references `depth` levels deep; None for none."""
    if not depth:
        return None
    return {
        "depth": min(depth, settings.transitive_max_depth),
        "allow": list(settings.transitive_allow_prefixes),
        "deny": list(settings.transitive_deny_prefixes),
    }
