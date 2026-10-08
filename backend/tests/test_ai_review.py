from __future__ import annotations

import pytest

from app.ai_review import ai_review_status

# Metadata as skillspector 2.12.0 reports it, trimmed to the fields that matter here.
STATIC = {"llm_requested": False, "llm_available": False, "meta_analysis_applied": False}
COMPLETE = {"llm_requested": True, "llm_available": True, "meta_analysis_applied": True, "llm_calls_attempted": 5, "llm_calls_succeeded": 5}
BAD_KEY = {
    "llm_requested": True,
    "llm_available": False,
    "meta_analysis_applied": False,
    "llm_calls_attempted": 5,
    "llm_calls_succeeded": 0,
    "llm_degraded": True,
    "llm_error": "LLM analysis was requested but 5 of 5 LLM call(s) failed; results reflect static analysis only "
    "for the affected batch(es). Reasons: TP4 LLM batch failed: AnthropicAuthenticationError",
}
PARTLY_FAILED = {**BAD_KEY, "llm_available": True, "meta_analysis_applied": True, "llm_calls_succeeded": 3}
UNAVAILABLE = {
    "llm_requested": True,
    "llm_available": False,
    "meta_analysis_applied": False,
    "llm_error": "LLM analysis was requested but unavailable during preflight; results reflect static analysis only.",
}


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        (STATIC, None),
        (COMPLETE, "complete"),
        (BAD_KEY, "failed"),
        (UNAVAILABLE, "failed"),
        (PARTLY_FAILED, "degraded"),
    ],
)
def test_ai_review_status_follows_the_report(metadata, expected):
    assert ai_review_status({"metadata": metadata}) == expected


def test_no_report_means_no_ai_review():
    assert ai_review_status(None) is None
    assert ai_review_status({}) is None
