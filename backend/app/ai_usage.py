"""Token usage of a scan's AI review, from skillspector's report metadata.

skillspector records one `metadata.inference_usage` entry per provider response, with the counters
the provider reported (see its docs/INFERENCE_USAGE.md). `prompt_tokens` already includes cached
input. A missing counter means the provider didn't report it, not zero, so totals only add what
was reported. skillspector attaches no prices, and neither does this.
"""

from __future__ import annotations

from typing import Any, NamedTuple


class TokenTotals(NamedTuple):
    input: int | None
    output: int | None
    cached: int | None


def token_totals(result: dict[str, Any] | None) -> TokenTotals:
    """Input, output and cache-read tokens over a scan's AI calls; None for counters never reported."""
    records = ((result or {}).get("metadata") or {}).get("inference_usage") or []

    def total(field: str) -> int | None:
        values = [r[field] for r in records if isinstance(r, dict) and isinstance(r.get(field), int)]
        return sum(values) if values else None

    return TokenTotals(total("prompt_tokens"), total("completion_tokens"), total("cached_tokens"))
