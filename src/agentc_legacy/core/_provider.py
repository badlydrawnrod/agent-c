"""Provider building and validation for Agent C."""

import os
from typing import Any

from .types import AgentConfig, PersonalityConfig


def validate_personality(
    personality_name: str,
    personalities: dict[str, PersonalityConfig],
    agent_configs: dict[str, AgentConfig],
    provider_override: str | None = None,
) -> tuple[PersonalityConfig, AgentConfig]:
    """Validate personality and return config objects.

    Args:
        personality_name: Name of the personality to validate.
        personalities: Available personalities.
        agent_configs: Available agent configurations.
        provider_override: CLI-provided provider override (optional).

    Returns:
        Tuple of (personality_config, agent_config).

    Raises:
        ValueError: If personality or provider is unsupported.
    """
    if personality_name not in personalities:
        raise ValueError(f"Unsupported personality: {personality_name}")
    personality = personalities[personality_name]
    provider_name = provider_override or personality.provider
    if provider_name not in agent_configs:
        raise ValueError(f"Unsupported provider: {provider_name}")
    config = agent_configs[provider_name]
    return personality, config


def build_provider(config: AgentConfig) -> Any:
    """Build the provider instance with necessary kwargs.

    Args:
        config: AgentConfig containing provider configuration.

    Returns:
        Instantiated provider.

    Raises:
        ValueError: If required API key environment variable is not set.
    """
    if config.api_key_env and not os.environ.get(config.api_key_env):
        raise ValueError(
            f"{config.api_key_env} environment variable is required for provider."
        )
    provider_kwargs = {}
    if config.api_key_env:
        provider_kwargs["api_key"] = os.environ.get(config.api_key_env)
    if config.base_url:
        provider_kwargs["base_url"] = config.base_url
    return config.provider_cls(**provider_kwargs)
