"""Agent factory and creation logic for Agent C.

This module orchestrates the creation of agent instances by coordinating
provider initialization, model configuration, and system prompt loading.
"""

from typing import Any

from pydantic_ai import Agent, DeferredToolRequests

from ._model import build_model
from ._prompt import build_system_prompt
from ._provider import build_provider, validate_personality
from .tools import ToolRegistry
from .types import AgentConfig, PersonalityConfig, RunDeps


def create_agent(
    personality_name: str,
    personalities: dict[str, PersonalityConfig],
    agent_configs: dict[str, AgentConfig],
    model_override: str | None = None,
    provider_override: str | None = None,
) -> Agent[RunDeps, str | DeferredToolRequests]:
    """Create an agent based on the specified personality.

    This function orchestrates the agent creation process:
    1. Validate personality and resolve provider config
    2. Instantiate the provider
    3. Build the model
    4. Build the system prompt (base + delegation info)
    5. Get tools from registry
    6. Create and return configured agent

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
    # 1. Validate personality and resolve provider config
    personality, config = validate_personality(
        personality_name, personalities, agent_configs, provider_override
    )

    # 2. Instantiate the provider
    provider = build_provider(config)

    # 3. Build the model
    model = build_model(config, personality, model_override, provider)

    # 4. Build the system prompt (base + delegation info)
    system_prompt = build_system_prompt(personality, personality_name, personalities)

    # 5. Get tools from registry
    # Google/Gemini models appear to struggle with strict tool validation.
    is_google = config.provider_cls.__module__.startswith("pydantic_ai.providers.google")
    registry = ToolRegistry(strict=not is_google)
    tools = registry.get_all()

    # 6. Create and return configured agent
    agent: Agent[RunDeps, str | DeferredToolRequests] = Agent(
        model=model,  # type: ignore
        tools=tools,
        system_prompt=system_prompt,
        deps_type=RunDeps,
        output_type=str | DeferredToolRequests,
    )
    return agent


def create_agent_factory(
    personalities: dict[str, PersonalityConfig],
    agent_configs: dict[str, AgentConfig],
    model_override: str | None = None,
    provider_override: str | None = None,
) -> Any:
    """Create a factory function for delegating to other agents.

    Returns a callable that takes a personality name and returns an Agent.

    Args:
        personalities: Available personalities.
        agent_configs: Available agent configurations.
        model_override: CLI-provided model override (optional).
        provider_override: CLI-provided provider override (optional).

    Returns:
        Callable factory that creates agents for delegation.
    """

    def factory(personality_name: str) -> Agent[RunDeps, str | DeferredToolRequests]:
        return create_agent(
            personality_name,
            personalities,
            agent_configs,
            model_override,
            provider_override,
        )

    return factory
