"""Model building for Agent C."""

from typing import Any

from .types import AgentConfig, PersonalityConfig


def build_model(
    config: AgentConfig,
    personality: PersonalityConfig,
    model_override: str | None,
    provider: Any,
) -> Any:
    """Build the model instance.

    Args:
        config: AgentConfig containing default model configuration.
        personality: PersonalityConfig which may override the model.
        model_override: CLI-provided model override (highest precedence).
        provider: Instantiated provider.

    Returns:
        Instantiated model.
    """
    model_name = model_override or personality.model or config.model_name
    return config.model_cls(model_name, provider=provider)
