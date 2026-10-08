"""The models skillspector knows for each provider, to suggest on the scan form.

Read from the model registries skillspector ships with each provider
(skillspector/providers/<provider>/model_registry.yaml), which list the models whose token limits
it knows. Any other model still works: the form takes a custom one.
"""

from __future__ import annotations

import functools
import importlib
from pathlib import Path
from typing import get_args

import yaml

from app.scanner import LLMProvider


@functools.cache
def model_catalog() -> dict[str, dict[str, object]]:
    """{provider: {"default": the model skillspector picks without one, "models": [...]}}."""
    catalog: dict[str, dict[str, object]] = {}
    for provider in get_args(LLMProvider):
        try:
            module = importlib.import_module(f"skillspector.providers.{provider}.provider")
        except ImportError:
            continue
        default = next(
            (cls.DEFAULT_MODEL for cls in vars(module).values() if isinstance(cls, type) and getattr(cls, "DEFAULT_MODEL", None)),
            None,
        )
        registry = Path(module.__file__).with_name("model_registry.yaml")
        models: list[str] = []
        if registry.is_file():
            models = list((yaml.safe_load(registry.read_text()) or {}).get("models") or {})
        if default and default not in models:
            models.insert(0, default)
        catalog[provider] = {"default": default, "models": models}
    return catalog
