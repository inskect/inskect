"""Whether a scan's AI review actually ran, from skillspector's report metadata.

A scan can ask for AI review and still come back with static results only: a wrong key, a provider
that's down, calls failing partway. skillspector records it (`llm_requested`, `llm_error`,
`llm_degraded`, `llm_calls_attempted` / `llm_calls_succeeded`), but the verdict alone looks the same.
"""

from __future__ import annotations

from typing import Any, Literal

AIReview = Literal["complete", "degraded", "failed"]


def ai_review_status(result: dict[str, Any] | None) -> AIReview | None:
    """None when no AI review was asked for; otherwise whether it ran fully, partly or not at all."""
    meta = (result or {}).get("metadata") or {}
    if not meta.get("llm_requested"):
        return None
    if not meta.get("llm_error") and not meta.get("llm_degraded"):
        return "complete"
    # Without call counts, nothing reached the provider (it was unavailable before the first call).
    if not meta.get("llm_calls_succeeded"):
        return "failed"
    return "degraded"
