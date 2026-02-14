"""Configuration dataclasses for provider and model presets.

Separated from event types to keep configuration concerns cohesive and
avoid the shared ``types`` module becoming a catch-all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BackendConfig:
    """Configuration for a model backend loaded from TOML."""

    name: str
    provider_cls_path: str  # e.g., "pydantic_ai.providers.anthropic.AnthropicProvider"
    model_cls_path: str  # e.g., "pydantic_ai.models.anthropic.AnthropicModel"
    api_key_env: str | None = None
    base_url_env: str | None = None
    base_url: str | None = None


@dataclass
class ModelConfig:
    """Configuration for a model preset bound to a backend."""

    name: str
    backend: str
    model_name: str
    api_key_env: str | None = None
    base_url_env: str | None = None
    base_url: str | None = None
    params: dict[str, Any] = field(default_factory=dict)


__all__ = ["BackendConfig", "ModelConfig"]
