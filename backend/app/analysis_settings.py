"""skillspector's own analysis settings, set by operators for every scan.

skillspector reads these from its environment. Only the ones listed in SKILLSPECTOR_ENV are passed
on, from INSKECT_* settings, never the API's whole environment: a scan run elsewhere gets
them as its own environment (skillspector_env), and a local scan from this process's, set by
apply_to_process before skillspector is imported, because it reads some of them only then.
Extra YARA rules aren't an environment variable: each scan is handed the directory instead.
"""

from __future__ import annotations

import os

from app.core.config import AnalysisSettings

# Each setting, and the skillspector variable it sets.
SKILLSPECTOR_ENV = {
    "output_language": "SKILLSPECTOR_OUTPUT_LANGUAGE",
    "reasoning_effort": "SKILLSPECTOR_REASONING_EFFORT",
    "temperature": "SKILLSPECTOR_TEMPERATURE",
    "max_llm_concurrency": "SKILLSPECTOR_MAX_LLM_CONCURRENCY",
    "osv_timeout_seconds": "SKILLSPECTOR_OSV_TIMEOUT",
    "max_workflow_seconds": "SKILLSPECTOR_MAX_WORKFLOW_SECONDS",
    "max_static_analysis_seconds_per_artifact": "SKILLSPECTOR_MAX_STATIC_ANALYSIS_SECONDS_PER_ARTIFACT",
}


def skillspector_env(settings: AnalysisSettings) -> dict[str, str]:
    """skillspector's variables for the settings that are set; the others keep its defaults."""
    env: dict[str, str] = {}
    for name, variable in SKILLSPECTOR_ENV.items():
        value = getattr(settings, name)
        if value is not None:
            env[variable] = f"{value:g}" if isinstance(value, float) else str(value)
    return env


def apply_to_process() -> None:
    """Set them for this process's local scans. Call it before anything imports skillspector."""
    os.environ.update(skillspector_env(AnalysisSettings()))
