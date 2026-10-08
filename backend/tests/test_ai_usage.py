from __future__ import annotations

from app.ai_usage import TokenTotals, token_totals


def _report(*records: dict) -> dict:
    return {"metadata": {"llm_requested": True, "inference_usage": list(records)}}


def test_tokens_add_up_over_every_ai_call():
    report = _report(
        {"node": "semantic_security_discovery", "prompt_tokens": 1000, "completion_tokens": 100, "cached_tokens": 400},
        {"node": "meta_analyzer", "prompt_tokens": 500, "completion_tokens": 50, "cached_tokens": 0},
    )
    assert token_totals(report) == TokenTotals(input=1500, output=150, cached=400)


def test_a_counter_no_provider_reported_stays_unknown():
    # A missing counter isn't a zero (skillspector's docs/INFERENCE_USAGE.md).
    report = _report({"node": "meta_analyzer", "prompt_tokens": 500, "completion_tokens": 50})
    assert token_totals(report) == TokenTotals(input=500, output=50, cached=None)


def test_static_scans_and_old_reports_have_no_tokens():
    assert token_totals({"metadata": {"llm_requested": False, "inference_usage": []}}) == TokenTotals(None, None, None)
    assert token_totals({}) == TokenTotals(None, None, None)
    assert token_totals(None) == TokenTotals(None, None, None)
