"""Agent factory and creation logic for Agent C.

This module handles the creation of agent instances, including provider
initialization, model configuration, system prompt loading, and command-line
argument parsing.
"""

import argparse
import os
from pathlib import Path
from typing import Any

from pydantic_ai import Agent, DeferredToolRequests

from .tools import ToolRegistry
from .types import AgentConfig, PersonalityConfig, RunDeps


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


def load_system_prompt(personality: PersonalityConfig) -> str:
    """Load the system prompt from file.

    Args:
        personality: PersonalityConfig containing the prompt file name.

    Returns:
        System prompt content.
    """
    with open(
        Path(__file__).parent.parent / "prompts" / personality.prompt_file,
        "r",
        encoding="utf-8",
    ) as f:
        return f.read()


def build_delegation_info(
    personality_name: str, personalities: dict[str, PersonalityConfig]
) -> str:
    """Build delegation instructions.

    This creates instructions informing the agent about available personalities
    it can delegate tasks to.

    Args:
        personality_name: Name of the current personality.
        personalities: All available personalities.

    Returns:
        Formatted delegation instructions.
    """
    return (
        "\n\nDelegation Instructions:\nYou can delegate tasks to other personalities using the delegate_to_agent tool if the task better fits their expertise.\n\nAvailable personalities:\n"
        + "\n".join(
            f"- {name}: {config.description}"
            for name, config in personalities.items()
            if name != personality_name
        )
    )


def parse_args(
    personalities: dict[str, PersonalityConfig],
    agent_configs: dict[str, AgentConfig],
) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        personalities: Available personalities for choice validation.
        agent_configs: Available agent configurations for provider validation.

    Returns:
        Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Run the agent with different personalities."
    )
    parser.add_argument(
        "--personality",
        choices=list(personalities.keys()),
        default="coder",
        help="Personality to use (default: coder)",
    )
    parser.add_argument(
        "--model",
        help="Override the default model for the selected personality",
    )
    parser.add_argument(
        "--provider",
        choices=list(agent_configs.keys()),
        help="Override the default provider for the selected personality",
    )
    return parser.parse_args()


def create_agent(
    personality_name: str,
    personalities: dict[str, PersonalityConfig],
    agent_configs: dict[str, AgentConfig],
    model_override: str | None = None,
    provider_override: str | None = None,
) -> Agent[RunDeps, str | DeferredToolRequests]:
    """Create an agent based on the specified personality.

    This is the main entry point for agent creation. It validates the
    personality, configures the provider and model, loads the system prompt,
    and instantiates the agent with all tools from the registry.

    Args:
        personality_name: Name of the personality to instantiate.
        personalities: Available personalities.
        agent_configs: Available agent configurations.
        model_override: CLI-provided model override (optional).
        provider_override: CLI-provided provider override (optional).

    Returns:
        Configured Agent instance.

    Raises:
        ValueError: If personality or provider validation fails.
    """
    personality, config = validate_personality(
        personality_name, personalities, agent_configs, provider_override
    )
    provider = build_provider(config)
    model = build_model(config, personality, model_override, provider)
    system_prompt = load_system_prompt(personality) + build_delegation_info(
        personality_name, personalities
    )

    # Create tool registry and get all tools
    registry = ToolRegistry()
    tools = registry.get_all()

    agent: Agent[RunDeps, str | DeferredToolRequests] = Agent(
        model=model,  # type: ignore
        tools=tools,
        system_prompt=system_prompt,
        deps_type=RunDeps,
        output_type=str | DeferredToolRequests,
    )
    return agent


def discover_tools() -> str:
    """Discover and format information about available tools.

    Returns:
        Formatted string describing all available tools.
    """
    registry = ToolRegistry()
    return registry.discover()
